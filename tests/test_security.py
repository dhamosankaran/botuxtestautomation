"""Unit tests for backend/security.py — triple-gate enforcement."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.security import (
    _check_for_leak,
    can_activate_red_team,
    check_allowlist,
)


# ---------------------------------------------------------------------------
# check_allowlist
# ---------------------------------------------------------------------------


def test_allowlist_matches_localhost(tmp_path):
    """Localhost URL matches the default localhost pattern."""
    allowlist = {
        "approved_targets": [
            {"url_pattern": "http://localhost:*/**", "notes": "Local"}
        ]
    }
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(allowlist))

    assert check_allowlist("http://localhost:8080/chatbot", str(path)) is True


def test_allowlist_no_match(tmp_path):
    """Production URL does not match localhost-only allowlist."""
    allowlist = {
        "approved_targets": [
            {"url_pattern": "http://localhost:*/**", "notes": "Local"}
        ]
    }
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(allowlist))

    assert check_allowlist("https://www.citi.com", str(path)) is False


def test_allowlist_wildcard_pattern(tmp_path):
    """Wildcard patterns match subdirectories correctly."""
    allowlist = {
        "approved_targets": [
            {"url_pattern": "https://staging.example.com/**", "notes": "Staging"}
        ]
    }
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(allowlist))

    assert check_allowlist("https://staging.example.com/chat/bot", str(path)) is True
    assert check_allowlist("https://prod.example.com/chat/bot", str(path)) is False


def test_allowlist_missing_file_returns_false():
    """Missing allowlist file returns False (safe default)."""
    assert check_allowlist("https://example.com", "nonexistent_path.json") is False


def test_allowlist_invalid_json_returns_false(tmp_path):
    """Malformed JSON allowlist returns False."""
    path = tmp_path / "bad.json"
    path.write_text("NOT VALID JSON {{{")
    assert check_allowlist("https://example.com", str(path)) is False


# ---------------------------------------------------------------------------
# Triple-gate: can_activate_red_team
# ---------------------------------------------------------------------------


def test_red_team_disabled_by_default(tmp_path):
    """Without --red-team flag, activation is always False."""
    allowlist = {
        "approved_targets": [
            {"url_pattern": "http://localhost:*/**", "notes": "Local"}
        ]
    }
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(allowlist))

    result = can_activate_red_team(
        target_url="http://localhost:8080/",
        red_team_flag=False,  # Gate 1 fails
        allowlist_path=str(path),
        require_confirmation=False,
    )
    assert result is False


def test_red_team_blocked_without_allowlist(tmp_path):
    """Flag alone is not sufficient — allowlist must also match."""
    allowlist = {"approved_targets": []}
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(allowlist))

    result = can_activate_red_team(
        target_url="https://www.citi.com",
        red_team_flag=True,  # Gate 1 passes
        allowlist_path=str(path),
        require_confirmation=False,
    )
    assert result is False  # Gate 2 fails


def test_red_team_requires_all_three_gates(tmp_path):
    """All three gates must pass for activation."""
    allowlist = {
        "approved_targets": [
            {"url_pattern": "http://localhost:*/**", "notes": "Local"}
        ]
    }
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(allowlist))

    with patch("backend.security.confirm_red_team", return_value=True):
        result = can_activate_red_team(
            target_url="http://localhost:8080/",
            red_team_flag=True,
            allowlist_path=str(path),
            require_confirmation=True,
        )
    assert result is True


def test_red_team_blocked_by_user_decline(tmp_path):
    """User declining the confirmation blocks activation even with flag + allowlist."""
    allowlist = {
        "approved_targets": [
            {"url_pattern": "http://localhost:*/**", "notes": "Local"}
        ]
    }
    path = tmp_path / "allowlist.json"
    path.write_text(json.dumps(allowlist))

    with patch("backend.security.confirm_red_team", return_value=False):
        result = can_activate_red_team(
            target_url="http://localhost:8080/",
            red_team_flag=True,
            allowlist_path=str(path),
            require_confirmation=True,
        )
    assert result is False


# ---------------------------------------------------------------------------
# _check_for_leak
# ---------------------------------------------------------------------------


def test_check_for_leak_detects_system_prompt():
    """Detects obvious system prompt leak in response."""
    assert _check_for_leak("My system prompt says to always be helpful.") is True


def test_check_for_leak_detects_instructions():
    """Detects 'my instructions' phrasing."""
    assert _check_for_leak("I was told to never discuss competitor products.") is True


def test_check_for_leak_clean_response():
    """Normal deflection response is not flagged as a leak."""
    assert _check_for_leak("I can't help with that request, but I can assist with...") is False


def test_check_for_leak_empty_response():
    """Empty response is not flagged as a leak."""
    assert _check_for_leak("") is False


# ---------------------------------------------------------------------------
# run_observe_only (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observe_only_returns_observations():
    """run_observe_only returns at least one observation."""
    from backend.security import run_observe_only

    mock_page = MagicMock()
    with patch("backend.security.get_dom_snapshot", new=AsyncMock(return_value="<html></html>")):
        observations = await run_observe_only(mock_page, widget_ctx=None)

    assert isinstance(observations, list)
    assert len(observations) >= 1
    assert all("timestamp" in o and "message" in o for o in observations)


@pytest.mark.asyncio
async def test_observe_only_flags_llm_indicators():
    """run_observe_only flags DOM content mentioning LLM providers."""
    from backend.security import run_observe_only

    dom_with_indicator = "<html><body>Powered by OpenAI</body></html>"
    mock_page = MagicMock()
    with patch("backend.security.get_dom_snapshot",
               new=AsyncMock(return_value=dom_with_indicator)):
        observations = await run_observe_only(mock_page, widget_ctx=None)

    messages = [o["message"] for o in observations]
    assert any("openai" in m.lower() or "LLM" in m or "provider" in m.lower()
               for m in messages)
