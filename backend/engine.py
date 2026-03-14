"""OBSERVE-REASON-ACT engine with FSM state management.

State machine: INIT → NAVIGATING → WIDGET_DETECTION → CONVERSATION_ACTIVE
               → GOAL_CHECK → [COMPLETE | FAILED | ESCALATED | ERROR]
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import async_playwright

from backend.mcp_browser import (
    WidgetContext,
    capture_screenshot,
    detect_chat_widget,
    execute_pre_steps,
    extract_chat_messages,
    get_dom_snapshot,
    launch_browser,
    navigate_to_url,
    send_chat_message,
    wait_for_bot_response,
)
from backend.reasoning import AgentDecision, call_reason, lookup_mock_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FSM state enum
# ---------------------------------------------------------------------------


class EngineState(Enum):
    """Finite state machine states for the test session lifecycle."""

    INIT = "INIT"
    NAVIGATING = "NAVIGATING"
    WIDGET_DETECTION = "WIDGET_DETECTION"
    CONVERSATION_ACTIVE = "CONVERSATION_ACTIVE"
    GOAL_CHECK = "GOAL_CHECK"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Session state container
# ---------------------------------------------------------------------------


@dataclass
class ConversationEntry:
    """One recorded turn in the conversation."""

    turn: int
    sender: str  # "user" | "bot" | "system"
    content: str
    timestamp: datetime
    bot_response_ms: Optional[int] = None
    agent_reasoning: Optional[str] = None


@dataclass
class SessionState:
    """Mutable state for a single scenario test run."""

    scenario: dict
    run_id: str
    report_dir: Path
    state: EngineState = EngineState.INIT
    turn: int = 0
    history: list[ConversationEntry] = field(default_factory=list)
    last_bot_messages: list[str] = field(default_factory=list)
    consecutive_empty: int = 0  # For bot_unresponsive detection
    consecutive_errors: int = 0  # For circuit breaker
    widget_ctx: Optional[WidgetContext] = None
    widget_detection_method: str = ""
    errors: list[dict] = field(default_factory=list)
    bot_response_times: list[int] = field(default_factory=list)
    last_send_time: Optional[datetime] = None  # Timestamp of most recent outbound message
    final_status: str = "PARTIAL"
    probe_results: list[dict] = field(default_factory=list)  # Red-team probe records

    @property
    def is_terminated(self) -> bool:
        """True when the FSM is in any terminal state."""
        return self.state in (
            EngineState.COMPLETE,
            EngineState.FAILED,
            EngineState.ESCALATED,
            EngineState.ERROR,
        )

    @property
    def max_turns(self) -> int:
        """Max turns from scenario config, with fallback default."""
        return int(self.scenario.get("max_turns", 20))

    def record(self, sender: str, content: str, bot_ms: Optional[int] = None,
               reasoning: Optional[str] = None) -> None:
        """Append a conversation entry to history."""
        self.history.append(ConversationEntry(
            turn=self.turn,
            sender=sender,
            content=content,
            timestamp=datetime.now(timezone.utc),
            bot_response_ms=bot_ms,
            agent_reasoning=reasoning,
        ))

    def add_error(self, turn: int, error_type: str, detail: str,
                  recovered: bool = False) -> None:
        """Record an error event."""
        self.errors.append({"turn": turn, "type": error_type,
                             "detail": detail, "recovered": recovered})


# ---------------------------------------------------------------------------
# Escalation detection helpers
# ---------------------------------------------------------------------------

_ESCALATION_PHRASES = [
    "transfer you to", "connect you to", "human agent", "live agent",
    "speak to a representative", "call us at", "1-800", "1-888", "1-877",
    "hold while i connect", "escalating your request",
]


def _detect_escalation(text: str) -> bool:
    """Return True if ``text`` contains human-escalation signals.

    Args:
        text: Bot response string.

    Returns:
        True if escalation detected.
    """
    lower = text.lower()
    return any(phrase in lower for phrase in _ESCALATION_PHRASES)


# ---------------------------------------------------------------------------
# OBSERVE step
# ---------------------------------------------------------------------------


async def observe(session: SessionState, settings: dict) -> list[str]:
    """Capture new bot messages since the last observation.

    Args:
        session: Current session state (must have widget_ctx).
        settings: Agent settings dict.

    Returns:
        List of new bot message texts. Empty list if bot did not respond.
    """
    if not session.widget_ctx:
        return []

    timeout_ms = settings.get("bot_response_timeout_ms", 10_000)
    stabilization_ms = settings.get("stabilization_delay_ms", 500)

    await wait_for_bot_response(
        frame=session.widget_ctx.frame,
        messages_selector=session.widget_ctx.messages_selector,
        timeout_ms=timeout_ms,
        stabilization_ms=stabilization_ms,
    )

    all_messages = await extract_chat_messages(session.widget_ctx)
    bot_messages = [m.text for m in all_messages if m.sender == "bot"]

    # Diff against previous observation
    prev = session.last_bot_messages
    new_messages = bot_messages[len(prev):]
    session.last_bot_messages = bot_messages
    return new_messages


# ---------------------------------------------------------------------------
# ACT step
# ---------------------------------------------------------------------------


async def act(decision: AgentDecision, session: SessionState,
              page: Any, settings: dict) -> str:
    """Execute the decision produced by the REASON step.

    Args:
        decision: Validated AgentDecision from reasoning.py.
        session: Current session state.
        page: Playwright Page object.
        settings: Agent settings dict.

    Returns:
        Status string: "sent" | "mock_data_sent" | "terminated" | "probe_sent".
    """
    mock_data: dict = session.scenario.get("mock_data", {})

    if decision.action == "respond":
        utterance = decision.utterance or ""
        await send_chat_message(utterance, session.widget_ctx)
        session.last_send_time = datetime.now(timezone.utc)  # Start latency timer
        session.record("user", utterance)
        return "sent"

    if decision.action == "provide_mock_data":
        value = lookup_mock_data(decision.mock_data_type or "account_number", mock_data)
        await send_chat_message(value, session.widget_ctx)
        session.last_send_time = datetime.now(timezone.utc)  # Start latency timer
        session.record("user", f"[mock:{decision.mock_data_type}] {value}")
        return "mock_data_sent"

    if decision.action == "probe":
        # Security module handles probes; engine just logs
        logger.info("Probe action delegated to security module")
        return "probe_sent"

    if decision.action == "terminate":
        reason = decision.termination_reason or "unknown"
        logger.info("Terminating: %s (confidence=%.2f)", reason, decision.confidence)
        session.record("system", f"Session terminated: {reason}")
        _apply_termination(session, reason)
        return "terminated"

    logger.warning("Unknown action '%s'; skipping", decision.action)
    return "noop"


def _apply_termination(session: SessionState, reason: str) -> None:
    """Transition FSM to the appropriate terminal state.

    Args:
        session: Current session state.
        reason: Termination reason string.
    """
    if reason == "goal_reached":
        session.state = EngineState.COMPLETE
        session.final_status = "PASS"
    elif reason == "human_escalation":
        session.state = EngineState.ESCALATED
        session.final_status = "FAIL"
    else:
        session.state = EngineState.FAILED
        session.final_status = "FAIL"


# ---------------------------------------------------------------------------
# Main reasoning loop
# ---------------------------------------------------------------------------


async def reasoning_loop(session: SessionState, page: Any, settings: dict) -> None:
    """Run the OBSERVE → REASON → ACT loop until a terminal state.

    Args:
        session: Current session state (must be in CONVERSATION_ACTIVE).
        page: Playwright Page.
        settings: Full settings dict (agent, browser, llm sections).
    """
    agent_cfg = settings.get("agent", {})
    scenario = session.scenario

    while not session.is_terminated:
        session.turn += 1
        logger.info("=== Turn %d/%d ===", session.turn, session.max_turns)

        # OBSERVE
        new_messages = await observe(session, agent_cfg)
        latest_bot = new_messages[-1] if new_messages else ""

        if not latest_bot:
            session.consecutive_empty += 1
            logger.warning("No bot response (empty count: %d)", session.consecutive_empty)
            if session.consecutive_empty >= 3:
                session.state = EngineState.FAILED
                session.final_status = "FAIL"
                session.record("system", "Bot unresponsive after 3 consecutive empty responses")
                break
        else:
            session.consecutive_empty = 0
            # Record bot response latency (ms since last outbound message)
            if session.last_send_time is not None:
                elapsed_ms = int(
                    (datetime.now(timezone.utc) - session.last_send_time).total_seconds() * 1000
                )
                session.bot_response_times.append(elapsed_ms)
                logger.debug("Bot responded in %dms", elapsed_ms)
                session.last_send_time = None
            session.record("bot", latest_bot)

        # Check escalation in bot message
        if latest_bot and _detect_escalation(latest_bot):
            logger.info("Human escalation detected")
            session.state = EngineState.ESCALATED
            session.final_status = "FAIL"
            session.record("system", "Human escalation detected")
            break

        # Check max turns
        if session.turn >= session.max_turns:
            logger.info("Max turns (%d) reached", session.max_turns)
            session.state = EngineState.FAILED
            session.final_status = "PARTIAL"
            session.record("system", f"Max turns ({session.max_turns}) reached")
            break

        # REASON
        history_msgs = [
            {"role": "user" if e.sender == "user" else "assistant", "content": e.content}
            for e in session.history if e.sender in ("user", "bot")
        ]

        llm_cfg = settings.get("llm", {})
        provider = llm_cfg.get("provider", "auto")
        model = llm_cfg.get("model") or None
        max_tokens = int(llm_cfg.get("max_tokens", 1024))

        try:
            decision = await call_reason(
                scenario_goal=scenario.get("goal", ""),
                success_criteria=[c.get("description", "") for c in
                                   scenario.get("success_criteria", [])],
                conversation_history=history_msgs,
                latest_bot_message=latest_bot,
                mock_data=scenario.get("mock_data", {}),
                provider=None if provider == "auto" else provider,
                model=model or None,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.error("REASON step failed: %s", exc)
            session.add_error(session.turn, "llm_error", str(exc), recovered=False)
            session.consecutive_errors += 1
            if session.consecutive_errors >= 5:
                logger.critical(
                    "Intra-session circuit breaker: %d consecutive LLM errors",
                    session.consecutive_errors,
                )
                session.state = EngineState.ERROR
                session.final_status = "ERROR"
                session.record(
                    "system",
                    f"Circuit breaker triggered: {session.consecutive_errors} consecutive LLM errors",
                )
                break
            continue

        session.record("system", f"REASON: action={decision.action} "
                       f"confidence={decision.confidence:.2f}",
                       reasoning=decision.action)

        # ACT
        result = await act(decision, session, page, settings)
        logger.debug("ACT result: %s", result)

        # GOAL_CHECK after each turn
        if decision.confidence >= 0.8 and decision.action != "terminate":
            logger.info("Goal confidence %.2f >= 0.8 → COMPLETE", decision.confidence)
            session.state = EngineState.COMPLETE
            session.final_status = "PASS"
            session.record("system", f"Goal reached. Confidence: {decision.confidence:.2f}")
            break

        if result == "terminated":
            break


# ---------------------------------------------------------------------------
# Top-level run function
# ---------------------------------------------------------------------------


async def run_scenario(scenario: dict, settings: dict, run_id: str,
                       red_team: bool = False) -> SessionState:
    """Execute a full scenario: browser → widget → conversation → report.

    Args:
        scenario: Parsed scenario YAML dict.
        settings: Parsed settings.yaml dict.
        run_id: Unique run identifier (timestamp-based).
        red_team: Whether red-team mode was requested via CLI.

    Returns:
        Completed SessionState with final status and history.
    """
    report_dir = Path(settings.get("reporting", {}).get("output_dir", "./reports")) / run_id
    report_dir.mkdir(parents=True, exist_ok=True)

    session = SessionState(scenario=scenario, run_id=run_id, report_dir=report_dir)
    browser_cfg = settings.get("browser", {})
    agent_cfg = settings.get("agent", {})
    started_at = datetime.now(timezone.utc)

    async with async_playwright() as playwright:
        browser, context, page = await launch_browser(
            playwright,
            headless=browser_cfg.get("headless", True),
            stealth=browser_cfg.get("stealth", True),
            viewport=browser_cfg.get("viewport"),
            chrome_user_data_dir=browser_cfg.get("chrome_user_data_dir"),
            slow_mo=int(browser_cfg.get("slow_mo", 0)),
        )

        try:
            session.state = EngineState.NAVIGATING
            target_url = scenario.get("target_url", "")
            session.record("system", f"Navigated to {target_url}")
            await navigate_to_url(page, target_url)

            # Run pre-steps (login, navigation clicks, etc.) before widget detection
            pre_steps = scenario.get("pre_steps", [])
            if pre_steps:
                logger.info("Running %d pre-step(s)...", len(pre_steps))
                try:
                    await execute_pre_steps(page, pre_steps)
                    session.record("system", f"Completed {len(pre_steps)} pre-step(s)")
                except RuntimeError as exc:
                    logger.error("Pre-step failed: %s", exc)
                    session.state = EngineState.ERROR
                    session.final_status = "ERROR"
                    session.record("system", f"PRE_STEP_FAILED — {exc}")
                    await _save_failure_artifacts(page, session, "pre_step_failed")
                    return session

            session.state = EngineState.WIDGET_DETECTION
            entry = scenario.get("entry_point", {})
            selectors = [entry.get("widget_selector")] + entry.get("fallback_selectors", [])
            selectors = [s for s in selectors if s]

            widget_ctx = await detect_chat_widget(page, selectors)
            if not widget_ctx:
                session.state = EngineState.ERROR
                session.final_status = "ERROR"
                session.record("system", "WIDGET_NOT_FOUND — no chat widget detected")
                await _save_failure_artifacts(page, session, "widget_not_found")
                return session

            session.widget_ctx = widget_ctx
            session.widget_detection_method = "primary_selector"
            session.record("system", "Chat widget detected")

            # Seed last_bot_messages with any greeting already in the DOM so that
            # the first observe() diff only returns the bot's REPLY to our opening
            # message, not the pre-existing greeting.
            initial_messages = await extract_chat_messages(widget_ctx)
            session.last_bot_messages = [m.text for m in initial_messages
                                         if m.sender == "bot"]
            logger.info("Seeded %d initial bot message(s) before opening turn",
                        len(session.last_bot_messages))

            # Send opening message
            opening = scenario.get("opening_message", "Hello")
            session.state = EngineState.CONVERSATION_ACTIVE
            await send_chat_message(opening, widget_ctx)
            session.last_send_time = datetime.now(timezone.utc)  # Start latency timer for turn 1
            session.record("user", opening)

            await reasoning_loop(session, page, settings)

        except Exception as exc:
            logger.error("Critical engine error: %s", exc, exc_info=True)
            session.state = EngineState.ERROR
            session.final_status = "ERROR"
            session.add_error(session.turn, "critical_error", str(exc))
            await _save_failure_artifacts(page, session, f"crash_turn_{session.turn}")
        finally:
            await context.close()
            if browser is not None:  # None in persistent context mode
                await browser.close()

    session.record("system", f"Run complete: {session.final_status}")
    return session


async def _save_failure_artifacts(page: Any, session: SessionState,
                                   label: str) -> None:
    """Save screenshot + DOM snapshot on critical failure.

    Args:
        page: Playwright Page.
        session: Current session state.
        label: File name prefix for the artifacts.
    """
    errors_dir = session.report_dir / "errors"
    errors_dir.mkdir(parents=True, exist_ok=True)
    await capture_screenshot(page, str(errors_dir / f"{label}.png"))
    try:
        dom = await get_dom_snapshot(page)
        (errors_dir / f"{label}.html").write_text(dom, encoding="utf-8")
        logger.info("DOM snapshot saved: %s", label)
    except Exception as exc:
        logger.error("DOM snapshot failed: %s", exc)
