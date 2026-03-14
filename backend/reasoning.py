"""LLM reasoning module — REASON step of the OBSERVE-REASON-ACT loop.

Guardrail 1: structured outputs enforced per provider:
  - OpenAI:    response_format json_schema (no markdown fences)
  - Google:    response_mime_type=application/json with schema
  - Anthropic: tool calling with make_decision (forced tool_choice)

Provider is selected via LLM_PROVIDER env var or config/settings.yaml.
Output is always validated with AgentDecision (Pydantic) before ACT.
"""
import json
import logging
import os
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

# Optional imports — whichever provider is installed will work
try:
    import anthropic as _anthropic_module
except ImportError:
    _anthropic_module = None  # type: ignore[assignment]

try:
    import openai as _openai_module
except ImportError:
    _openai_module = None  # type: ignore[assignment]

try:
    from google import genai as _genai
    from google.genai import types as _genai_types
except ImportError:
    _genai = None  # type: ignore[assignment]
    _genai_types = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Anthropic tool schema (kept for reference / Anthropic provider path)
# ---------------------------------------------------------------------------

MAKE_DECISION_TOOL: dict[str, Any] = {
    "name": "make_decision",
    "description": (
        "Decide the next action to take in the chatbot test conversation. "
        "Choose 'respond' to send a message, 'provide_mock_data' to supply "
        "synthetic personal data the bot requested, 'probe' for security testing "
        "(only when red-team is enabled and target is allowlisted), or 'terminate' "
        "when the scenario is complete or stuck."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["respond", "probe", "provide_mock_data", "terminate"],
            },
            "utterance": {"type": "string"},
            "mock_data_type": {
                "type": "string",
                "enum": ["pin", "account_number", "ssn_last4"],
            },
            "termination_reason": {
                "type": "string",
                "enum": ["goal_reached", "human_escalation", "stuck", "max_turns"],
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["action", "confidence"],
    },
}

# OpenAI JSON schema (Guardrail 1 for OpenAI)
_OPENAI_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "agent_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["respond", "probe", "provide_mock_data", "terminate"],
                },
                "utterance": {"type": ["string", "null"]},
                "mock_data_type": {
                    "type": ["string", "null"],
                    "enum": ["pin", "account_number", "ssn_last4", None],
                },
                "termination_reason": {
                    "type": ["string", "null"],
                    "enum": [
                        "goal_reached", "human_escalation", "stuck", "max_turns", None
                    ],
                },
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
            "required": ["action", "utterance", "mock_data_type", "termination_reason", "confidence"],
            "additionalProperties": False,
        },
    },
}


# ---------------------------------------------------------------------------
# AgentDecision Pydantic model — validated before every ACT step
# ---------------------------------------------------------------------------


class AgentDecision(BaseModel):
    """Structured decision from the REASON step, validated before ACT.

    Crashes fast on invalid values rather than propagating bad state.
    """

    action: str  # respond | probe | provide_mock_data | terminate
    utterance: Optional[str] = None
    mock_data_type: Optional[str] = None  # pin | account_number | ssn_last4
    termination_reason: Optional[str] = None  # goal_reached | human_escalation | stuck | max_turns
    confidence: float = Field(ge=0.0, le=1.0)

    def model_post_init(self, __context: Any) -> None:
        """Reject unknown action values immediately."""
        valid = {"respond", "probe", "provide_mock_data", "terminate"}
        if self.action not in valid:
            raise ValueError(f"Invalid action '{self.action}'. Must be one of {valid}")


# ---------------------------------------------------------------------------
# System prompt (shared across all providers)
# ---------------------------------------------------------------------------

_QA_SYSTEM_PROMPT = (
    "You are an experienced QA engineer conducting a structured conversation with a "
    "chatbot to evaluate whether it meets defined success criteria.\n\n"
    "Rules:\n"
    "1. Drive the conversation naturally toward the scenario goal.\n"
    "2. Evaluate each bot response against the success criteria.\n"
    "3. Use 'provide_mock_data' when the bot requests personal information.\n"
    "4. Use 'terminate' with reason 'goal_reached' when confidence > 0.8.\n"
    "5. Use 'terminate' with reason 'human_escalation' if the bot transfers to a human.\n"
    "6. Use 'terminate' with reason 'stuck' after 3 consecutive unhelpful responses.\n"
    "Respond ONLY with the JSON decision object — no explanation, no markdown."
)


# ---------------------------------------------------------------------------
# Provider-specific callers
# ---------------------------------------------------------------------------


async def _call_openai(prompt: str, history: list[dict], model: str,
                       max_tokens: int) -> dict:
    """Call OpenAI with json_schema response format (Guardrail 1).

    Args:
        prompt: Context message with goal, criteria, and latest bot message.
        history: Last N conversation turns.
        model: OpenAI model name (e.g. gpt-4o-mini).
        max_tokens: Max completion tokens.

    Returns:
        Raw dict parsed from JSON response.
    """
    if _openai_module is None:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in environment")

    client = _openai_module.AsyncOpenAI(api_key=api_key)
    messages = [{"role": "system", "content": _QA_SYSTEM_PROMPT}]
    messages += history[-10:]
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        response_format=_OPENAI_RESPONSE_FORMAT,
        messages=messages,
    )
    content = response.choices[0].message.content or "{}"
    logger.debug("OpenAI raw response: %s", content[:200])
    return json.loads(content)


async def _call_gemini(prompt: str, history: list[dict], model: str,
                       max_tokens: int) -> dict:
    """Call Google Gemini with JSON mode (Guardrail 1).

    Uses the google-genai SDK (v1+). Enforces JSON output via
    response_mime_type so no markdown fences can contaminate the output.

    Args:
        prompt: Context message.
        history: Last N conversation turns.
        model: Gemini model name (e.g. gemini-2.0-flash).
        max_tokens: Max output tokens.

    Returns:
        Raw dict parsed from JSON response.
    """
    if _genai is None:
        raise RuntimeError(
            "google-genai not installed. Run: pip install google-genai"
        )

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not set in environment")

    history_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Bot'}: {m['content']}"
        for m in history[-10:]
    )
    full_prompt = f"{_QA_SYSTEM_PROMPT}\n\n{history_text}\n\nContext:\n{prompt}"

    client = _genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model=model,
        contents=full_prompt,
        config=_genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
            temperature=0.2,
        ),
    )
    raw_text = response.text
    logger.debug("Gemini raw response: %s", raw_text[:200])
    return json.loads(raw_text)


async def _call_anthropic(prompt: str, history: list[dict], model: str,
                           max_tokens: int) -> dict:
    """Call Anthropic Claude with forced tool calling (Guardrail 1).

    Args:
        prompt: Context message.
        history: Last N conversation turns.
        model: Anthropic model name.
        max_tokens: Max tokens.

    Returns:
        Raw dict from tool call input.
    """
    if _anthropic_module is None:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in environment")

    client = _anthropic_module.AsyncAnthropic(api_key=api_key)
    messages = list(history[-10:])
    messages.append({"role": "user", "content": prompt})

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_QA_SYSTEM_PROMPT,
        tools=[MAKE_DECISION_TOOL],
        tool_choice={"type": "tool", "name": "make_decision"},
        messages=messages,
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "make_decision":
            return block.input  # type: ignore[return-value]
    raise RuntimeError("No make_decision tool call in Anthropic response")


# ---------------------------------------------------------------------------
# Public interface: call_reason
# ---------------------------------------------------------------------------


async def call_reason(
    scenario_goal: str,
    success_criteria: list[str],
    conversation_history: list[dict],
    latest_bot_message: str,
    mock_data: dict,
    red_team_enabled: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> AgentDecision:
    """Call the configured LLM provider and return a validated AgentDecision.

    Provider resolution order:
      1. ``provider`` argument
      2. LLM_PROVIDER environment variable
      3. First available provider with a configured API key

    Args:
        scenario_goal: High-level goal from the scenario YAML.
        success_criteria: List of criterion description strings.
        conversation_history: Prior turns as {"role": ..., "content": ...} dicts.
        latest_bot_message: Most recent bot response text.
        mock_data: Dict of synthetic data from mock_data.json.
        red_team_enabled: Whether red-team probing is active.
        provider: Override provider ("openai", "google", "anthropic").
        model: Override model name.
        max_tokens: Max response tokens.

    Returns:
        Validated AgentDecision.

    Raises:
        RuntimeError: On API failure or unparseable/invalid response.
    """
    resolved_provider = provider or os.environ.get("LLM_PROVIDER") or _detect_provider()
    resolved_model = model or _default_model(resolved_provider)

    criteria_text = "\n".join(f"- {c}" for c in success_criteria)
    context_prompt = (
        f"SCENARIO GOAL: {scenario_goal}\n\n"
        f"SUCCESS CRITERIA:\n{criteria_text}\n\n"
        f"LATEST BOT MESSAGE: {latest_bot_message or '(none yet)'}\n\n"
        f"MOCK DATA AVAILABLE: {json.dumps(mock_data)}\n"
        f"RED-TEAM ENABLED: {red_team_enabled}"
    )

    logger.info("REASON step — provider=%s model=%s", resolved_provider, resolved_model)

    try:
        if resolved_provider == "openai":
            raw = await _call_openai(context_prompt, conversation_history,
                                     resolved_model, max_tokens)
        elif resolved_provider in ("google", "gemini"):
            raw = await _call_gemini(context_prompt, conversation_history,
                                     resolved_model, max_tokens)
        elif resolved_provider == "anthropic":
            raw = await _call_anthropic(context_prompt, conversation_history,
                                        resolved_model, max_tokens)
        else:
            raise RuntimeError(f"Unknown LLM provider: '{resolved_provider}'")
    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        raise RuntimeError(f"LLM call failed: {exc}") from exc

    return _validate_decision(raw)


def _detect_provider() -> str:
    """Auto-detect provider from available API keys.

    Returns:
        Provider name string.

    Raises:
        RuntimeError: If no recognised API key is set.
    """
    if os.environ.get("OPENAI_API_KEY"):
        logger.info("Auto-detected provider: openai")
        return "openai"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        logger.info("Auto-detected provider: google")
        return "google"
    if os.environ.get("ANTHROPIC_API_KEY"):
        logger.info("Auto-detected provider: anthropic")
        return "anthropic"
    raise RuntimeError(
        "No LLM API key found. Set one of: OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY"
    )


def _default_model(provider: str) -> str:
    """Return the default model name for a provider.

    Args:
        provider: Provider name string.

    Returns:
        Default model name string.
    """
    env_model = os.environ.get("GEMINI_MODEL") or os.environ.get("LLM_MODEL", "")
    defaults = {
        "openai": "gpt-4o-mini",
        "google": env_model or "gemini-2.0-flash",
        "gemini": env_model or "gemini-2.0-flash",
        "anthropic": "claude-opus-4-6",
    }
    return defaults.get(provider, "gpt-4o-mini")


def _validate_decision(raw: dict) -> AgentDecision:
    """Validate raw LLM output with Pydantic before passing to ACT.

    Args:
        raw: Dict from JSON/tool response.

    Returns:
        Validated AgentDecision.

    Raises:
        RuntimeError: On validation failure.
    """
    try:
        decision = AgentDecision.model_validate(raw)
        logger.info("Decision: action=%s confidence=%.2f", decision.action, decision.confidence)
        return decision
    except ValidationError as exc:
        logger.error("AgentDecision validation failed: %s | raw=%s", exc, raw)
        raise RuntimeError(f"Invalid agent decision: {exc}") from exc


# ---------------------------------------------------------------------------
# Mock data lookup
# ---------------------------------------------------------------------------


def lookup_mock_data(data_type: str, mock_data: dict) -> str:
    """Return the synthetic data value for a given type.

    Args:
        data_type: One of "pin", "account_number", "ssn_last4".
        mock_data: Dict loaded from config/mock_data.json.

    Returns:
        String value, or a safe default if the key is missing.
    """
    defaults = {
        "pin": "0000",
        "account_number": "4111-0000-0000-1234",
        "ssn_last4": "0000",
    }
    value = mock_data.get(data_type, defaults.get(data_type, "0000"))
    logger.debug("Mock data lookup: %s → %s", data_type, value)
    return str(value)
