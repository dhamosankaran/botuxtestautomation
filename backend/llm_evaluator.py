"""LLM Evaluator service using Google Gemini for quality assessment."""
import os
import json
from typing import Optional
from dataclasses import dataclass
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print(f"LLM configured: model={GEMINI_MODEL}, temp={LLM_TEMPERATURE}")


@dataclass
class EvaluationResult:
    """Result of LLM evaluation for a bot response."""
    relevance_score: float  # 0-10: How relevant is the response?
    helpfulness_score: float  # 0-10: Does it solve the user's issue?
    clarity_score: float  # 0-10: Is the response clear and understandable?
    accuracy_score: float  # 0-10: Is the information accurate?
    overall_score: float  # Average of all scores
    sentiment: str  # positive, neutral, negative
    escalation_appropriate: bool  # Should this have been escalated?
    escalation_detected: bool  # Did the bot offer escalation?
    improvement_suggestion: str  # How to improve the response
    evaluation_notes: str  # Additional notes from LLM


EVALUATION_PROMPT = """You are an expert QA analyst evaluating a banking chatbot's responses.
Evaluate the following conversation and provide scores and feedback.

## User Question
{user_question}

## Bot Response
{bot_response}

## Expected Intent
{expected_intent}

## Evaluation Criteria

Score each on a scale of 0-10:
1. **Relevance**: Does the response address the user's question?
2. **Helpfulness**: Does it solve or progress toward solving the issue?
3. **Clarity**: Is the response clear, well-structured, and easy to understand?
4. **Accuracy**: Is the information provided accurate for a banking context?

Also determine:
- **Sentiment**: Is the bot's tone positive, neutral, or negative?
- **Escalation Appropriate**: Should this query have been escalated to a human?
- **Escalation Detected**: Did the bot offer to connect to a human agent?

Respond in this exact JSON format:
{{
    "relevance_score": <0-10>,
    "helpfulness_score": <0-10>,
    "clarity_score": <0-10>,
    "accuracy_score": <0-10>,
    "sentiment": "<positive|neutral|negative>",
    "escalation_appropriate": <true|false>,
    "escalation_detected": <true|false>,
    "improvement_suggestion": "<brief suggestion to improve the response>",
    "evaluation_notes": "<any additional observations>"
}}
"""


def evaluate_response(
    user_question: str,
    bot_response: str,
    expected_intent: str = ""
) -> Optional[EvaluationResult]:
    """
    Evaluate a bot response using Gemini LLM.
    
    Args:
        user_question: The user's original question
        bot_response: The chatbot's response
        expected_intent: Description of what the bot should do
    
    Returns:
        EvaluationResult with scores and feedback, or None if evaluation fails
    """
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not set. Skipping LLM evaluation.")
        return _create_fallback_evaluation(bot_response)
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        generation_config = genai.types.GenerationConfig(
            temperature=LLM_TEMPERATURE,
            max_output_tokens=LLM_MAX_TOKENS,
        )
        
        prompt = EVALUATION_PROMPT.format(
            user_question=user_question,
            bot_response=bot_response if bot_response else "[No response received]",
            expected_intent=expected_intent if expected_intent else "Help the user with their banking question"
        )
        
        response = model.generate_content(prompt, generation_config=generation_config)
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)
            
            return EvaluationResult(
                relevance_score=float(data.get("relevance_score", 0)),
                helpfulness_score=float(data.get("helpfulness_score", 0)),
                clarity_score=float(data.get("clarity_score", 0)),
                accuracy_score=float(data.get("accuracy_score", 0)),
                overall_score=_calculate_overall(data),
                sentiment=data.get("sentiment", "neutral"),
                escalation_appropriate=data.get("escalation_appropriate", False),
                escalation_detected=data.get("escalation_detected", False),
                improvement_suggestion=data.get("improvement_suggestion", ""),
                evaluation_notes=data.get("evaluation_notes", "")
            )
        
        return _create_fallback_evaluation(bot_response)
        
    except Exception as e:
        print(f"LLM evaluation error: {e}")
        return _create_fallback_evaluation(bot_response)


def _calculate_overall(data: dict) -> float:
    """Calculate overall score as average of all scores."""
    scores = [
        float(data.get("relevance_score", 0)),
        float(data.get("helpfulness_score", 0)),
        float(data.get("clarity_score", 0)),
        float(data.get("accuracy_score", 0)),
    ]
    return round(sum(scores) / len(scores), 2) if scores else 0


def _create_fallback_evaluation(bot_response: str) -> EvaluationResult:
    """Create a basic evaluation without LLM (fallback)."""
    # Basic heuristics when LLM is not available
    has_response = bool(bot_response and len(bot_response) > 10)
    
    escalation_keywords = [
        "agent", "representative", "human", "call us", "phone",
        "1-800", "customer service", "speak to"
    ]
    escalation_detected = any(
        kw in bot_response.lower() for kw in escalation_keywords
    ) if bot_response else False
    
    return EvaluationResult(
        relevance_score=5.0 if has_response else 0.0,
        helpfulness_score=5.0 if has_response else 0.0,
        clarity_score=5.0 if has_response else 0.0,
        accuracy_score=5.0 if has_response else 0.0,
        overall_score=5.0 if has_response else 0.0,
        sentiment="neutral",
        escalation_appropriate=False,
        escalation_detected=escalation_detected,
        improvement_suggestion="LLM evaluation not available",
        evaluation_notes="Fallback evaluation used (no API key)"
    )


def batch_evaluate(
    conversations: list[tuple[str, str, str]]
) -> list[EvaluationResult]:
    """
    Evaluate multiple conversations.
    
    Args:
        conversations: List of (user_question, bot_response, expected_intent) tuples
    
    Returns:
        List of EvaluationResult objects
    """
    results = []
    for user_q, bot_r, intent in conversations:
        result = evaluate_response(user_q, bot_r, intent)
        results.append(result)
    return results


@dataclass
class AdaptiveDecision:
    """Decision from LLM for adaptive testing."""
    action: str  # CLICK_MENU, CONTINUE, PASS, FAIL
    menu_choice: str = ""  # Menu option to click (if CLICK_MENU)
    follow_up: str = ""  # Follow-up message (if CONTINUE)
    reason: str = ""  # Explanation for the decision
    score: float = 0.0  # Quality score (1-10)
    intent_identified: bool = False  # Did bot identify correct intent?
    flow_completed: bool = False  # Did bot complete the flow?


ADAPTIVE_PROMPT = """You are testing a banking chatbot. Analyze the bot's response and decide the next action.

## Customer Question
{utterance}

## Bot Response
{bot_response}

## Available Menu Options (if any)
{menu_options}

## CRITICAL RULES FOR CREDIT CARD TESTING
1. ALWAYS select CREDIT CARD options when available (e.g., "Citi Double Cash", "Citi Strata", "Citi Custom Cash")
2. NEVER select "Checking" or "Savings" accounts - SKIP them completely
3. If only checking/savings accounts are shown, choose CONTINUE and ask specifically about credit cards

## Instructions
1. If bot shows clickable menu options with a CREDIT CARD option, choose CLICK_MENU with that card
2. If bot asks "Which card?" or "Which account?", choose CONTINUE with "my credit card" or specific card name
3. If bot only shows checking/savings options, choose CONTINUE with "I want to check my credit card"
4. If bot successfully answered about a credit card, choose PASS
5. If bot didn't help or gave irrelevant response, choose FAIL

Skip menu options that navigate away (e.g., "View Account", "Go to Page", "See more").
Skip checking and savings accounts - focus ONLY on credit cards.

Respond in this exact JSON format:
{{
    "action": "<CLICK_MENU|CONTINUE|PASS|FAIL>",
    "menu_choice": "<exact menu text to click - MUST be a credit card option, or empty>",
    "follow_up": "<text to type if CONTINUE, or empty>",
    "reason": "<brief explanation>",
    "score": <1-10 quality rating>,
    "intent_identified": <true if bot understood what user wanted>,
    "flow_completed": <true if bot completed the task with credit card info>
}}
"""


def analyze_and_decide(
    utterance: str,
    bot_response: str,
    menu_options: list[str] = None
) -> AdaptiveDecision:
    """
    Analyze bot response and decide next action for adaptive testing.
    
    Args:
        utterance: The user's message/question
        bot_response: The bot's response text
        menu_options: List of available menu button texts
    
    Returns:
        AdaptiveDecision with action, menu_choice/follow_up, and scores
    """
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not set. Using fallback decision.")
        return _create_fallback_decision(utterance, bot_response)
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        generation_config = genai.types.GenerationConfig(
            temperature=LLM_TEMPERATURE,
            max_output_tokens=LLM_MAX_TOKENS,
        )
        
        # Format menu options
        menu_str = "\n".join(f"- {opt}" for opt in (menu_options or [])) or "No menu options available"
        
        prompt = ADAPTIVE_PROMPT.format(
            utterance=utterance,
            bot_response=bot_response if bot_response else "[No response received]",
            menu_options=menu_str
        )
        
        response = model.generate_content(prompt, generation_config=generation_config)
        response_text = response.text.strip()
        
        # Extract JSON from response
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)
            
            return AdaptiveDecision(
                action=data.get("action", "FAIL").upper(),
                menu_choice=data.get("menu_choice", ""),
                follow_up=data.get("follow_up", ""),
                reason=data.get("reason", ""),
                score=float(data.get("score", 0)),
                intent_identified=data.get("intent_identified", False),
                flow_completed=data.get("flow_completed", False)
            )
        
        return _create_fallback_decision(utterance, bot_response)
        
    except Exception as e:
        print(f"LLM adaptive decision error: {e}")
        return _create_fallback_decision(utterance, bot_response)


def _create_fallback_decision(utterance: str, bot_response: str) -> AdaptiveDecision:
    """Create a basic decision without LLM (fallback)."""
    has_response = bool(bot_response and len(bot_response) > 10)
    
    return AdaptiveDecision(
        action="PASS" if has_response else "FAIL",
        reason="Fallback decision (LLM unavailable)",
        score=5.0 if has_response else 0.0,
        intent_identified=has_response,
        flow_completed=has_response
    )

