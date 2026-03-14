"""Unit tests for backend/reasoning.py.

All LLM calls are mocked — no network access required.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.reasoning import (
    AgentDecision,
    MAKE_DECISION_TOOL,
    _validate_decision,
    lookup_mock_data,
)


# ---------------------------------------------------------------------------
# AgentDecision validation
# ---------------------------------------------------------------------------


def test_valid_respond_decision():
    """AgentDecision accepts a well-formed 'respond' action."""
    d = AgentDecision(action="respond", utterance="Hello!", confidence=0.5)
    assert d.action == "respond"
    assert d.confidence == 0.5


def test_valid_terminate_decision():
    """AgentDecision accepts a 'terminate' action with reason."""
    d = AgentDecision(
        action="terminate",
        termination_reason="goal_reached",
        confidence=0.9,
    )
    assert d.termination_reason == "goal_reached"


def test_valid_provide_mock_data():
    """AgentDecision accepts 'provide_mock_data' with a mock_data_type."""
    d = AgentDecision(
        action="provide_mock_data",
        mock_data_type="pin",
        confidence=0.6,
    )
    assert d.mock_data_type == "pin"


def test_confidence_too_high_raises():
    """Confidence > 1.0 raises a ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AgentDecision(action="respond", confidence=1.5)


def test_confidence_negative_raises():
    """Confidence < 0.0 raises a ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AgentDecision(action="respond", confidence=-0.1)


def test_invalid_action_raises():
    """Unrecognised action string raises a ValueError."""
    with pytest.raises(Exception):
        AgentDecision(action="maybe_respond", confidence=0.5)


# ---------------------------------------------------------------------------
# _validate_decision
# ---------------------------------------------------------------------------


def test_validate_decision_good_input():
    """_validate_decision returns AgentDecision for valid raw dict."""
    raw = {"action": "respond", "utterance": "Hello", "confidence": 0.7}
    d = _validate_decision(raw)
    assert isinstance(d, AgentDecision)
    assert d.action == "respond"


def test_validate_decision_bad_input_raises():
    """_validate_decision raises RuntimeError for invalid dict."""
    with pytest.raises(RuntimeError, match="Invalid agent decision"):
        _validate_decision({"action": "fly", "confidence": 99.0})


# ---------------------------------------------------------------------------
# MAKE_DECISION_TOOL schema
# ---------------------------------------------------------------------------


def test_tool_schema_has_required_fields():
    """The make_decision tool schema contains required fields."""
    schema = MAKE_DECISION_TOOL
    assert schema["name"] == "make_decision"
    props = schema["input_schema"]["properties"]
    assert "action" in props
    assert "confidence" in props
    required = schema["input_schema"]["required"]
    assert "action" in required
    assert "confidence" in required


def test_tool_schema_action_enum():
    """The action enum contains all four allowed values."""
    actions = MAKE_DECISION_TOOL["input_schema"]["properties"]["action"]["enum"]
    assert "respond" in actions
    assert "probe" in actions
    assert "provide_mock_data" in actions
    assert "terminate" in actions


# ---------------------------------------------------------------------------
# lookup_mock_data
# ---------------------------------------------------------------------------


def test_lookup_known_key():
    """lookup_mock_data returns the correct value for a known key."""
    data = {"pin": "1234", "account_number": "4111-0000-0000-1234"}
    assert lookup_mock_data("pin", data) == "1234"


def test_lookup_missing_key_returns_default():
    """lookup_mock_data returns a safe default for an unknown key."""
    result = lookup_mock_data("ssn_last4", {})
    assert result == "0000"


def test_lookup_account_number_default():
    """lookup_mock_data returns spec-defined test account number as default."""
    result = lookup_mock_data("account_number", {})
    assert result == "4111-0000-0000-1234"


# ---------------------------------------------------------------------------
# call_reason (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_reason_uses_openai_when_key_set(monkeypatch):
    """call_reason() uses OpenAI provider when OPENAI_API_KEY is set."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    expected_raw = {
        "action": "respond",
        "utterance": "What interest rates do you offer?",
        "mock_data_type": None,
        "termination_reason": None,
        "confidence": 0.6,
    }

    with patch("backend.reasoning._call_openai", new=AsyncMock(return_value=expected_raw)):
        from backend.reasoning import call_reason

        decision = await call_reason(
            scenario_goal="Get credit card info",
            success_criteria=["Bot mentions APR"],
            conversation_history=[],
            latest_bot_message="How can I help?",
            mock_data={"account_number": "4111-0000-0000-1234"},
        )

    assert isinstance(decision, AgentDecision)
    assert decision.action == "respond"
    assert 0.0 <= decision.confidence <= 1.0


@pytest.mark.asyncio
async def test_call_reason_uses_gemini_when_key_set(monkeypatch):
    """call_reason() uses Google provider when GEMINI_API_KEY is set (no OpenAI key)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    expected_raw = {
        "action": "terminate",
        "utterance": None,
        "mock_data_type": None,
        "termination_reason": "goal_reached",
        "confidence": 0.9,
    }

    with patch("backend.reasoning._call_gemini", new=AsyncMock(return_value=expected_raw)):
        from backend.reasoning import call_reason

        decision = await call_reason(
            scenario_goal="Get credit card info",
            success_criteria=["Bot mentions APR"],
            conversation_history=[],
            latest_bot_message="Our Rewards Card has APR 22.49%.",
            mock_data={},
        )

    assert decision.action == "terminate"
    assert decision.termination_reason == "goal_reached"


@pytest.mark.asyncio
async def test_call_reason_raises_without_any_api_key(monkeypatch):
    """call_reason() raises RuntimeError when no API keys are set."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    from backend.reasoning import call_reason

    with pytest.raises(RuntimeError):
        await call_reason(
            scenario_goal="Test",
            success_criteria=[],
            conversation_history=[],
            latest_bot_message="Hello",
            mock_data={},
        )
