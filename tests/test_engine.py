"""Unit tests for backend/engine.py — OBSERVE-REASON-ACT loop and FSM."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.engine import (
    EngineState,
    SessionState,
    _detect_escalation,
    _apply_termination,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(tmp_path: Path, max_turns: int = 20) -> SessionState:
    scenario = {
        "name": "Test",
        "target_url": "https://example.com",
        "goal": "Get credit card info",
        "max_turns": max_turns,
        "success_criteria": [{"description": "Bot mentions APR", "type": "contains_info"}],
        "mock_data": {"pin": "0000"},
        "opening_message": "Hello",
        "entry_point": {"widget_selector": "#chat-widget", "fallback_selectors": []},
    }
    return SessionState(
        scenario=scenario,
        run_id="test-run-001",
        report_dir=tmp_path / "reports" / "test-run-001",
    )


# ---------------------------------------------------------------------------
# FSM state transitions
# ---------------------------------------------------------------------------


def test_initial_state_is_init(tmp_path):
    """SessionState starts in INIT state."""
    session = _make_session(tmp_path)
    assert session.state == EngineState.INIT


def test_is_terminated_false_on_init(tmp_path):
    """is_terminated is False for non-terminal states."""
    session = _make_session(tmp_path)
    assert session.is_terminated is False


def test_is_terminated_true_on_complete(tmp_path):
    """is_terminated is True when state is COMPLETE."""
    session = _make_session(tmp_path)
    session.state = EngineState.COMPLETE
    assert session.is_terminated is True


def test_is_terminated_true_on_failed(tmp_path):
    """is_terminated is True when state is FAILED."""
    session = _make_session(tmp_path)
    session.state = EngineState.FAILED
    assert session.is_terminated is True


def test_is_terminated_true_on_error(tmp_path):
    """is_terminated is True when state is ERROR."""
    session = _make_session(tmp_path)
    session.state = EngineState.ERROR
    assert session.is_terminated is True


# ---------------------------------------------------------------------------
# _detect_escalation
# ---------------------------------------------------------------------------


def test_detect_escalation_human_agent():
    """Detects 'human agent' escalation phrase."""
    assert _detect_escalation("I'll connect you to a human agent now.") is True


def test_detect_escalation_toll_free():
    """Detects toll-free number as escalation signal."""
    assert _detect_escalation("Please call us at 1-800-555-0000.") is True


def test_detect_escalation_false_for_normal_text():
    """Normal bot response is not flagged as escalation."""
    assert _detect_escalation("We offer three credit card options.") is False


# ---------------------------------------------------------------------------
# _apply_termination
# ---------------------------------------------------------------------------


def test_apply_termination_goal_reached(tmp_path):
    """goal_reached → COMPLETE + PASS status."""
    session = _make_session(tmp_path)
    _apply_termination(session, "goal_reached")
    assert session.state == EngineState.COMPLETE
    assert session.final_status == "PASS"


def test_apply_termination_human_escalation(tmp_path):
    """human_escalation → ESCALATED + FAIL status."""
    session = _make_session(tmp_path)
    _apply_termination(session, "human_escalation")
    assert session.state == EngineState.ESCALATED
    assert session.final_status == "FAIL"


def test_apply_termination_stuck(tmp_path):
    """stuck → FAILED + FAIL status."""
    session = _make_session(tmp_path)
    _apply_termination(session, "stuck")
    assert session.state == EngineState.FAILED
    assert session.final_status == "FAIL"


# ---------------------------------------------------------------------------
# session.record and session.add_error
# ---------------------------------------------------------------------------


def test_session_record_appends_entry(tmp_path):
    """session.record() adds entries to history."""
    session = _make_session(tmp_path)
    session.record("user", "Hello bot")
    session.record("bot", "Hi there!")
    assert len(session.history) == 2
    assert session.history[0].sender == "user"
    assert session.history[1].content == "Hi there!"


def test_session_add_error(tmp_path):
    """session.add_error() appends to the errors list."""
    session = _make_session(tmp_path)
    session.add_error(3, "selector_timeout", "Selector #foo not found", recovered=True)
    assert len(session.errors) == 1
    assert session.errors[0]["type"] == "selector_timeout"
    assert session.errors[0]["recovered"] is True


# ---------------------------------------------------------------------------
# Max turns boundary
# ---------------------------------------------------------------------------


def test_max_turns_from_scenario(tmp_path):
    """max_turns property reads from scenario dict."""
    session = _make_session(tmp_path, max_turns=15)
    assert session.max_turns == 15


# ---------------------------------------------------------------------------
# reasoning_loop (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_goal_reached(tmp_path):
    """reasoning_loop terminates with COMPLETE when confidence >= 0.8."""
    from backend.engine import reasoning_loop
    from backend.reasoning import AgentDecision

    session = _make_session(tmp_path, max_turns=5)
    session.state = EngineState.CONVERSATION_ACTIVE

    # Set up a mock widget context
    mock_frame = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.frame = mock_frame
    mock_ctx.messages_selector = "#message-list"
    session.widget_ctx = mock_ctx

    settings = {
        "agent": {
            "bot_response_timeout_ms": 2000,
            "stabilization_delay_ms": 100,
        }
    }

    high_confidence_decision = AgentDecision(
        action="respond",
        utterance="Tell me about APR.",
        confidence=0.9,
    )

    with (
        patch("backend.engine.observe", new=AsyncMock(return_value=["Bot response text"])),
        patch("backend.engine.call_reason", new=AsyncMock(return_value=high_confidence_decision)),
        patch("backend.engine.send_chat_message", new=AsyncMock()),
    ):
        await reasoning_loop(session, MagicMock(), settings)

    assert session.state == EngineState.COMPLETE
    assert session.final_status == "PASS"


@pytest.mark.asyncio
async def test_max_turns_exceeded(tmp_path):
    """reasoning_loop terminates with GOAL_CHECK when max_turns is hit."""
    from backend.engine import reasoning_loop
    from backend.reasoning import AgentDecision

    session = _make_session(tmp_path, max_turns=2)
    session.state = EngineState.CONVERSATION_ACTIVE
    session.widget_ctx = MagicMock()
    session.widget_ctx.frame = MagicMock()
    session.widget_ctx.messages_selector = "#message-list"

    low_confidence = AgentDecision(action="respond", utterance="Hello",
                                   confidence=0.3)

    settings = {"agent": {"bot_response_timeout_ms": 1000, "stabilization_delay_ms": 100}}

    with (
        patch("backend.engine.observe", new=AsyncMock(return_value=["Bot says hi"])),
        patch("backend.engine.call_reason", new=AsyncMock(return_value=low_confidence)),
        patch("backend.engine.send_chat_message", new=AsyncMock()),
    ):
        await reasoning_loop(session, MagicMock(), settings)

    assert session.is_terminated
    assert session.final_status in ("FAIL", "PARTIAL")


@pytest.mark.asyncio
async def test_bot_unresponsive_terminates(tmp_path):
    """reasoning_loop sets FAILED after 3 consecutive empty responses."""
    from backend.engine import reasoning_loop

    session = _make_session(tmp_path, max_turns=20)
    session.state = EngineState.CONVERSATION_ACTIVE
    session.widget_ctx = MagicMock()
    session.widget_ctx.frame = MagicMock()
    session.widget_ctx.messages_selector = "#message-list"

    settings = {"agent": {"bot_response_timeout_ms": 1000, "stabilization_delay_ms": 100}}

    with patch("backend.engine.observe", new=AsyncMock(return_value=[])):
        await reasoning_loop(session, MagicMock(), settings)

    assert session.state == EngineState.FAILED


@pytest.mark.asyncio
async def test_human_escalation_detected(tmp_path):
    """reasoning_loop sets ESCALATED when bot response contains escalation phrase."""
    from backend.engine import reasoning_loop
    from backend.reasoning import AgentDecision

    session = _make_session(tmp_path, max_turns=10)
    session.state = EngineState.CONVERSATION_ACTIVE
    session.widget_ctx = MagicMock()
    session.widget_ctx.frame = MagicMock()
    session.widget_ctx.messages_selector = "#message-list"

    settings = {"agent": {"bot_response_timeout_ms": 1000, "stabilization_delay_ms": 100}}

    with patch("backend.engine.observe",
               new=AsyncMock(return_value=["I'll transfer you to a human agent now."])):
        await reasoning_loop(session, MagicMock(), settings)

    assert session.state == EngineState.ESCALATED
