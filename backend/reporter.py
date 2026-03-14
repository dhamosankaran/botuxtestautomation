"""Report and transcript generation for completed test runs.

Produces: report.json, transcript.txt, security.log (if red-team enabled),
and a formatted Rich console summary.
"""
import json
import logging
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sentiment scoring (post-processing LLM call)
# ---------------------------------------------------------------------------


async def score_sentiments(bot_messages: list[str]) -> list[float]:
    """Score the sentiment of each bot message using the available LLM provider.

    Makes a single batched call after the conversation completes.
    Scores are on a scale from -1.0 (very negative) to 1.0 (very positive),
    with 0.0 being neutral.

    Args:
        bot_messages: Ordered list of bot response strings.

    Returns:
        List of float scores, one per message.  Falls back to 0.0 per message
        on any error so that report generation is never blocked.
    """
    if not bot_messages:
        return []

    numbered = "\n".join(f"{i + 1}. {msg}" for i, msg in enumerate(bot_messages))
    prompt = (
        "Score the sentiment of each bot message below on a scale from -1.0 "
        "(very negative/hostile/unhelpful) to 1.0 (very positive/helpful/warm). "
        "0.0 is neutral.\n\n"
        "Return ONLY a valid JSON array of numbers, one number per message, "
        "in the same order.  No explanation.\n\n"
        f"Messages:\n{numbered}"
    )

    provider = os.environ.get("LLM_PROVIDER") or _detect_sentiment_provider()
    try:
        if provider == "anthropic":
            scores = await _sentiment_anthropic(prompt, len(bot_messages))
        elif provider == "openai":
            scores = await _sentiment_openai(prompt, len(bot_messages))
        else:
            logger.warning("Sentiment scoring: provider '%s' not supported — defaulting to 0.0", provider)
            return [0.0] * len(bot_messages)
        return [max(-1.0, min(1.0, float(s))) for s in scores]
    except Exception as exc:
        logger.warning("Sentiment scoring failed (%s) — defaulting to 0.0", exc)
        return [0.0] * len(bot_messages)


def _detect_sentiment_provider() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "none"


async def _sentiment_anthropic(prompt: str, expected: int) -> list[float]:
    try:
        import anthropic as _ant
    except ImportError:
        raise RuntimeError("anthropic package not installed")
    client = _ant.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    resp = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    scores = json.loads(raw)
    if isinstance(scores, list) and len(scores) == expected:
        return scores
    raise ValueError(f"Unexpected sentiment response length: got {len(scores)}, want {expected}")


async def _sentiment_openai(prompt: str, expected: int) -> list[float]:
    try:
        import openai as _oai
    except ImportError:
        raise RuntimeError("openai package not installed")
    client = _oai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = (resp.choices[0].message.content or "").strip()
    scores = json.loads(raw)
    if isinstance(scores, list) and len(scores) == expected:
        return scores
    raise ValueError(f"Unexpected sentiment response length: got {len(scores)}, want {expected}")


# ---------------------------------------------------------------------------
# Latency statistics
# ---------------------------------------------------------------------------


def _compute_latency(times_ms: list[int]) -> dict:
    """Calculate avg, max, and p95 latency from a list of millisecond values.

    Args:
        times_ms: List of response time values in milliseconds.

    Returns:
        Dict with avg_bot_response_ms, max_bot_response_ms, p95_bot_response_ms.
    """
    if not times_ms:
        return {"avg_bot_response_ms": 0, "max_bot_response_ms": 0,
                "p95_bot_response_ms": 0}
    sorted_times = sorted(times_ms)
    p95_index = max(0, int(len(sorted_times) * 0.95) - 1)
    return {
        "avg_bot_response_ms": int(statistics.mean(times_ms)),
        "max_bot_response_ms": max(times_ms),
        "p95_bot_response_ms": sorted_times[p95_index],
    }


# ---------------------------------------------------------------------------
# Success criteria evaluation
# ---------------------------------------------------------------------------


def evaluate_criteria(transcript_text: str, criteria: list[dict]) -> list[dict]:
    """Check which success criteria are met based on the conversation transcript.

    Simple keyword-match heuristic. The LLM confidence score is the authoritative
    source; this provides evidence-turn references.

    Args:
        transcript_text: Full transcript as a single string.
        criteria: List of {"description": str, "type": str} dicts from scenario.

    Returns:
        List of {"description", "met", "evidence_turn"} dicts.
    """
    results = []
    lines = transcript_text.splitlines()

    for criterion in criteria:
        desc = criterion.get("description", "")
        met = False
        evidence_turn = None

        # Look for BOT lines that contain content relevant to the criterion
        keywords = _extract_keywords(desc)
        for i, line in enumerate(lines):
            if "[BOT]" in line and any(kw in line.lower() for kw in keywords):
                met = True
                # Estimate turn number from line index
                bot_lines_before = sum(1 for l in lines[:i] if "[USER]" in l)
                evidence_turn = bot_lines_before
                break

        results.append({"description": desc, "met": met, "evidence_turn": evidence_turn})

    return results


def _extract_keywords(description: str) -> list[str]:
    """Extract meaningful keywords from a criterion description for matching.

    Args:
        description: Human-readable criterion description.

    Returns:
        List of lowercase keyword strings.
    """
    stop_words = {"a", "an", "the", "is", "are", "at", "bot", "provides",
                  "least", "one", "or", "and", "of", "to", "for"}
    words = description.lower().split()
    return [w.strip(".,;:()") for w in words if w not in stop_words and len(w) > 3]


# ---------------------------------------------------------------------------
# Report JSON generation
# ---------------------------------------------------------------------------


def generate_report_json(
    run_id: str,
    scenario: dict,
    session,  # SessionState — avoid circular import
    started_at: datetime,
    completed_at: datetime,
    transcript_text: str,
    sentiment_by_turn: Optional[dict] = None,
) -> dict:
    """Build the report.json data structure.

    Args:
        run_id: Unique run identifier.
        scenario: Parsed scenario YAML dict.
        session: Completed SessionState from engine.py.
        started_at: When the run started.
        completed_at: When the run finished.
        transcript_text: Full transcript string.
        sentiment_by_turn: Optional mapping of turn_number → sentiment score.

    Returns:
        Dict matching the report.json schema from the spec.
    """
    if sentiment_by_turn is None:
        sentiment_by_turn = {}

    duration = (completed_at - started_at).total_seconds()
    latency = _compute_latency(session.bot_response_times)
    criteria = evaluate_criteria(transcript_text, scenario.get("success_criteria", []))

    scores = list(sentiment_by_turn.values())
    avg_sentiment = round(statistics.mean(scores), 3) if scores else None

    return {
        "run_id": run_id,
        "scenario": scenario.get("name", "Unknown"),
        "target_url": scenario.get("target_url", ""),
        "status": session.final_status,
        "duration_seconds": round(duration, 2),
        "total_turns": session.turn,
        "widget_detected": session.widget_ctx is not None,
        "widget_detection_method": session.widget_detection_method,
        "success_criteria_results": criteria,
        "errors": session.errors,
        "latency": latency,
        "sentiment_by_turn": sentiment_by_turn,
        "avg_sentiment": avg_sentiment,
    }


def write_report_json(report_dir: Path, report: dict) -> Path:
    """Write report.json to the report directory.

    Args:
        report_dir: Path to the run's report directory.
        report: Report dict from generate_report_json().

    Returns:
        Path to the written file.
    """
    path = report_dir / "report.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    logger.info("Report written: %s", path)
    return path


# ---------------------------------------------------------------------------
# Transcript generation
# ---------------------------------------------------------------------------


def generate_transcript(session, run_id: str) -> str:
    """Build the transcript.txt content from session history.

    Format: [ISO-8601] [SENDER]   Message text

    Args:
        session: Completed SessionState.
        run_id: Used to label SYSTEM entries.

    Returns:
        Full transcript as a string.
    """
    lines: list[str] = []
    sender_map = {
        "user": "USER",
        "bot": "BOT",
        "system": "SYSTEM",
    }

    for entry in session.history:
        ts = entry.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        sender_label = sender_map.get(entry.sender, "SYSTEM")
        # Pad for alignment: SYSTEM=6, USER=4, BOT=3
        padding = " " * max(1, 6 - len(sender_label))
        if entry.agent_reasoning:
            lines.append(f"[{ts}] [AGENT_REASONING] {entry.agent_reasoning}")
        lines.append(f"[{ts}] [{sender_label}]{padding}{entry.content}")

    return "\n".join(lines)


def write_transcript(report_dir: Path, transcript: str) -> Path:
    """Write transcript.txt to the report directory.

    Args:
        report_dir: Path to the run's report directory.
        transcript: Transcript string from generate_transcript().

    Returns:
        Path to the written file.
    """
    path = report_dir / "transcript.txt"
    path.write_text(transcript, encoding="utf-8")
    logger.info("Transcript written: %s", path)
    return path


# ---------------------------------------------------------------------------
# Security log generation
# ---------------------------------------------------------------------------


def generate_security_log(probes: list[dict], run_id: str) -> str:
    """Build the security.log content from probe records.

    Format: [ISO-8601] [TYPE]  Message

    Args:
        probes: List of probe result dicts from security.py.
        run_id: Run identifier for header.

    Returns:
        Security log content as a string.
    """
    lines = [f"# Security Log — Run {run_id}"]
    for probe in probes:
        ts = probe.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        entry_type = probe.get("type", "OBSERVE").upper()
        message = probe.get("message", "")
        padding = " " * max(1, 7 - len(entry_type))
        lines.append(f"[{ts}] [{entry_type}]{padding}{message}")
    return "\n".join(lines)


def write_security_log(report_dir: Path, log_content: str) -> Path:
    """Write security.log to the report directory.

    Args:
        report_dir: Path to the run's report directory.
        log_content: Content from generate_security_log().

    Returns:
        Path to the written file.
    """
    path = report_dir / "security.log"
    path.write_text(log_content, encoding="utf-8")
    logger.info("Security log written: %s", path)
    return path


# ---------------------------------------------------------------------------
# Console summary (Rich)
# ---------------------------------------------------------------------------


def print_console_summary(report: dict, report_dir: Path) -> None:
    """Print a formatted summary to the console.

    Args:
        report: Report dict from generate_report_json().
        report_dir: Path to the report directory.
    """
    try:
        from rich.console import Console
        from rich.rule import Rule

        console = Console()
        status = report["status"]
        color = {"PASS": "green", "FAIL": "red", "ERROR": "yellow",
                 "PARTIAL": "orange3"}.get(status, "white")

        console.print(Rule("[bold blue]BOTTestAutomation[/bold blue]"))
        console.print(f"  Scenario:  {report['scenario']}")
        console.print(f"  Target:    {report['target_url']}")
        console.print(Rule(style="dim"))

        widget_icon = "✓" if report["widget_detected"] else "✗"
        console.print(f"  {widget_icon} Widget detected ({report['widget_detection_method']})")

        console.print(f"  Turns:     {report['total_turns']}")
        avg_ms = report["latency"].get("avg_bot_response_ms", 0)
        console.print(f"  Avg latency: {avg_ms}ms")

        console.print(Rule(style="dim"))
        console.print(
            f"  RESULT: [{color}]{status}[/{color}]  |  "
            f"{report['total_turns']} turns  |  {report['duration_seconds']}s"
        )
        console.print(f"  Reports: {report_dir}")
        console.print(Rule(style="blue"))

    except ImportError:
        # Fallback without Rich
        print(f"\n{'='*44}")
        print(f"BOTTestAutomation")
        print(f"Scenario:  {report['scenario']}")
        print(f"Target:    {report['target_url']}")
        print(f"RESULT: {report['status']} | {report['total_turns']} turns "
              f"| {report['duration_seconds']}s")
        print(f"Reports: {report_dir}")
        print(f"{'='*44}\n")
