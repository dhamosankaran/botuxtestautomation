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
    # Validate model availability
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        model_full_name = f"models/{GEMINI_MODEL}"
        if model_full_name not in available_models:
            print(f"WARNING: Model '{GEMINI_MODEL}' may not be available.")
            print(f"Available generation models: {[m.split('/')[-1] for m in available_models[:10]]}...")
        else:
            print(f"✓ Model '{GEMINI_MODEL}' validated successfully")
    except Exception as e:
        print(f"Could not validate model availability: {e}")
else:
    print("WARNING: GEMINI_API_KEY not set. LLM evaluation will use fallback mode.")


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


@dataclass
class ScreenshotAnalysis:
    """Result of Gemini Vision analysis of a chatbot screenshot."""
    bot_message: str  # The actual narrative text from the bot
    menu_options: list  # List of clickable menu options/buttons
    has_confirmation: bool  # Is this asking for Yes/No confirmation?
    has_card_selection: bool  # Is bot asking to select a card/account?
    recommended_action: str  # "CLICK_MENU", "TYPE_MESSAGE", "CONFIRM_YES", "CONFIRM_NO"
    recommended_choice: str  # Which option to click or what to type
    analysis_notes: str  # Additional observations


SCREENSHOT_ANALYSIS_PROMPT = """You are an expert at analyzing banking chatbot interfaces.

Analyze this screenshot of a chatbot conversation and extract the following information:

1. **Bot Message**: What is the actual narrative text the bot is saying? (NOT button labels)
2. **Menu Options**: List ALL clickable buttons, menu options, or quick replies visible
3. **Confirmation Question**: Is the bot asking a Yes/No confirmation question?
4. **Card/Account Selection**: Is the bot asking the user to select a card or account?
5. **Recommended Action**: Based on testing "card not working", what should we do next?

The user's original question was about their card not working. We want to progress through 
the flow to report or troubleshoot the card issue.

Respond in this exact JSON format:
{
    "bot_message": "<the actual bot narrative text, NOT button labels>",
    "menu_options": ["option1", "option2", "option3"],
    "has_confirmation": <true if asking Yes/No, otherwise false>,
    "has_card_selection": <true if showing card/account options, otherwise false>,
    "recommended_action": "<CLICK_MENU|TYPE_MESSAGE|CONFIRM_YES|CONFIRM_NO|WAIT>",
    "recommended_choice": "<which button to click or what to type>",
    "analysis_notes": "<any important observations about the chat state>"
}
"""


def analyze_screenshot_with_vision(
    screenshot_path: str,
    original_utterance: str = "",
    max_retries: int = 2
) -> Optional[ScreenshotAnalysis]:
    """
    Analyze a chatbot screenshot using Gemini Vision to extract bot message and menu options.
    
    This provides much more accurate understanding of what the bot is showing
    compared to DOM-based parsing.
    
    Args:
        screenshot_path: Path to the screenshot PNG file
        original_utterance: The original user question for context
        max_retries: Number of retries on failure
        
    Returns:
        ScreenshotAnalysis with extracted information, or None on failure
    """
    if not GEMINI_API_KEY:
        print("[Vision] No API key configured, skipping screenshot analysis")
        return None
    
    import PIL.Image
    
    for attempt in range(max_retries):
        try:
            # Load the image
            image = PIL.Image.open(screenshot_path)
            
            # Create the model with vision capability
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            # Build prompt with context
            prompt = SCREENSHOT_ANALYSIS_PROMPT
            if original_utterance:
                prompt = prompt.replace(
                    "card not working", 
                    original_utterance
                )
            
            # Generate analysis with increased token limit
            response = model.generate_content(
                [prompt, image],
                generation_config=genai.GenerationConfig(
                    temperature=0.2,  # Lower temperature for more consistent parsing
                    max_output_tokens=2048  # Increased from 1024 to prevent truncation
                )
            )
            
            response_text = response.text
            print(f"[Vision] Raw response length: {len(response_text)}")
            
            # Parse JSON response
            try:
                result = extract_json_from_response(response_text)
            except ValueError as json_err:
                # Fallback: Try a simpler prompt if JSON parsing fails
                print(f"[Vision] JSON parse failed, trying simpler extraction...")
                simple_prompt = """Look at this chatbot screenshot. Return ONLY valid JSON:
{"bot_message": "<what the bot is saying>", "menu_options": ["option1", "option2"], "recommended_choice": "<best option to click>"}"""
                
                simple_response = model.generate_content(
                    [simple_prompt, image],
                    generation_config=genai.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=512
                    )
                )
                result = extract_json_from_response(simple_response.text)
            
            analysis = ScreenshotAnalysis(
                bot_message=result.get("bot_message", ""),
                menu_options=result.get("menu_options", []),
                has_confirmation=result.get("has_confirmation", False),
                has_card_selection=result.get("has_card_selection", False),
                recommended_action=result.get("recommended_action", "CLICK_MENU"),
                recommended_choice=result.get("recommended_choice", ""),
                analysis_notes=result.get("analysis_notes", "")
            )
            
            print(f"[Vision] ✓ Bot message: {analysis.bot_message[:80]}...")
            print(f"[Vision] ✓ Menu options: {analysis.menu_options}")
            print(f"[Vision] ✓ Recommended: {analysis.recommended_action} -> {analysis.recommended_choice}")
            
            return analysis
            
        except Exception as e:
            print(f"[Vision] Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(1)
    
    return None


def extract_json_from_response(response_text: str, debug: bool = False) -> dict:
    """
    Extract JSON from LLM response, handling markdown code blocks and truncated responses.
    
    Args:
        response_text: Raw text from LLM response
        debug: If True, print debug information
        
    Returns:
        Parsed JSON as dict, raises ValueError if parsing fails
    """
    import re
    text = response_text.strip()
    original_text = text
    
    if debug:
        print(f"  [DEBUG] Input length: {len(text)}, starts with: {text[:30]}...")
    
    # Remove markdown code blocks if present (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split('\n')
        content_lines = []
        in_block = False
        
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            elif line.strip() == "```" and in_block:
                break
            elif in_block:
                content_lines.append(line)
        
        if content_lines:
            text = '\n'.join(content_lines)
            if debug:
                print(f"  [DEBUG] Extracted from code block, length: {len(text)}")
    
    # Find JSON object
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    
    if debug:
        print(f"  [DEBUG] json_start={json_start}, json_end={json_end}")
    
    if json_start < 0:
        raise ValueError(f"No JSON object found in response: {original_text[:150]}...")
    
    # Get JSON string (may be truncated)
    json_str = text[json_start:json_end] if json_end > json_start else text[json_start:]
    
    # Try parsing as-is first
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        if debug:
            print(f"  [DEBUG] Initial parse failed: {e}")
        
        # REPAIR TRUNCATED JSON: Add missing closing brackets/braces
        # Count open brackets and add closing ones
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')
        
        # Check if we're in a string (unfinished string literal)
        # Count quotes - odd number means we're inside a string
        quote_count = json_str.count('"') - json_str.count('\\"')
        if quote_count % 2 == 1:
            json_str += '"'  # Close the string
        
        # Add closing brackets
        json_str += ']' * open_brackets
        json_str += '}' * open_braces
        
        if debug:
            print(f"  [DEBUG] Repaired JSON: added {open_brackets} ] and {open_braces} }}")
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e2:
            # Last resort: try to extract key-value pairs manually
            if debug:
                print(f"  [DEBUG] Repair failed: {e2}, trying manual extraction")
            
            result = {}
            
            # Extract bot_message
            msg_match = re.search(r'"bot_message"\s*:\s*"([^"]*)"', json_str)
            if msg_match:
                result["bot_message"] = msg_match.group(1)
            
            # Extract menu_options as list
            opts_match = re.search(r'"menu_options"\s*:\s*\[(.*?)\]', json_str, re.DOTALL)
            if opts_match:
                opts_str = opts_match.group(1)
                options = re.findall(r'"([^"]+)"', opts_str)
                result["menu_options"] = options
            
            # Extract recommended_choice
            choice_match = re.search(r'"recommended_choice"\s*:\s*"([^"]*)"', json_str)
            if choice_match:
                result["recommended_choice"] = choice_match.group(1)
            
            # Extract recommended_action
            action_match = re.search(r'"recommended_action"\s*:\s*"([^"]*)"', json_str)
            if action_match:
                result["recommended_action"] = action_match.group(1)
            
            if result:
                if debug:
                    print(f"  [DEBUG] Manual extraction got: {result}")
                return result
            
            raise ValueError(f"No JSON object found in response: {original_text[:150]}...")


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
    expected_intent: str = "",
    max_retries: int = 3
) -> Optional[EvaluationResult]:
    """
    Evaluate a bot response using Gemini LLM.
    
    Args:
        user_question: The user's original question
        bot_response: The chatbot's response
        expected_intent: Description of what the bot should do
        max_retries: Number of retries on API failure
    
    Returns:
        EvaluationResult with scores and feedback, or None if evaluation fails
    """
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not set. Skipping LLM evaluation.")
        return _create_fallback_evaluation(bot_response)
    
    last_error = None
    
    for attempt in range(max_retries):
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
            
            # Extract JSON from response (handles markdown code blocks)
            try:
                data = extract_json_from_response(response_text)
                
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
            except ValueError as e:
                print(f"[Attempt {attempt+1}] {e}")
                last_error = str(e)
            
        except json.JSONDecodeError as e:
            print(f"[Attempt {attempt+1}] JSON parse error in evaluation: {e}")
            last_error = str(e)
        except Exception as e:
            print(f"[Attempt {attempt+1}] LLM evaluation error: {type(e).__name__}: {e}")
            last_error = str(e)
            
            # Wait before retry (exponential backoff)
            if attempt < max_retries - 1:
                import time
                wait_time = (2 ** attempt) * 0.5  # 0.5s, 1s, 2s
                print(f"  Retrying in {wait_time}s...")
                time.sleep(wait_time)
    
    print(f"LLM evaluation failed after {max_retries} attempts: {last_error}")
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

## Customer's Original Question
{utterance}

## Bot's Current Response
{bot_response}

## Available Menu Options (if any)
{menu_options}

## Previous Actions Taken (CRITICAL - AVOID REPEATING!)
{action_history}

## CRITICAL: Credit Card vs Banking Account Selection
When the bot asks "Is this for your credit card or banking account?" or similar:
- If customer mentioned CARD, CREDIT CARD, chip, declined, expired, damaged → select "My credit card"
- If customer mentioned CHECKING, SAVINGS, DEPOSIT, TRANSFER → select "My banking account"
- **NEVER click "None of these" if "My credit card" or "My banking account" is an option!**

Common CARD-RELATED keywords: card, credit, debit, ATM, chip, magnetic, declined, expired, damaged, lost, stolen, not working
Common ACCOUNT-RELATED keywords: checking, savings, deposit, balance, transfer, account

## CRITICAL: Recognize Confirmation Questions
The bot often asks confirmation questions that expect a "Yes" or "No" response:
- "Is that for [Account Name]?" → Click "Yes" to confirm
- "[Account Name], right?" → Click "Yes" to confirm
- "Just want to make sure..." → Click "Yes" to confirm
- "Is this correct?" → Click "Yes" if matches intent
- "Would you like to continue?" → Click "Yes" if making progress

**NEVER click the same account/option twice!** If you already clicked an account, the bot is asking for CONFIRMATION - click "Yes" instead.

## Card Account Selection
When bot shows a list of cards like "Citi Double Cash® Card...4685", "Citi Strata℠ Card...0252":
- Pick the FIRST credit card option if asking about credit cards
- These are actual card accounts - selecting one progresses the flow
- Don't select "Checking..." if the issue is about a credit CARD

## IMPORTANT: Understand the Customer's Intent
- CREDIT CARD issues (balance, payment, dispute, rewards, not working, damaged) → select credit card options
- CHECKING account → select checking account options  
- SAVINGS account → select savings account options
- TRANSFERS → follow transfer flow

## Handling YES/NO Confirmations
- If bot confirms the correct account/action → click "Yes"
- If bot asks about something wrong → click "No"
- IMPORTANT: Always click confirmations to continue the flow

## Decision Rules
1. Check if "My credit card" or "My banking account" is available - if user mentioned card, select "My credit card"
2. If bot shows menu options matching intent, choose CLICK_MENU with relevant option
3. If bot shows "Yes/No" confirmation, choose the appropriate response
4. If bot asks "Which account?", select a card if issue is card-related
5. If bot successfully answered with actual data (balance, etc.) → PASS
6. If bot gave irrelevant/error response → FAIL
7. If making progress → CONTINUE

## Signs of a FAIL response:
- "I'd be happy to give it another shot" (fallback)
- "I'm sorry, I didn't understand"
- "Please try again"
- Response completely unrelated to the question
- Feedback/survey request without resolving issue

## Signs of a PASS response:
- Bot provides requested information (balance, confirmation, etc.)
- Bot confirms an action was completed
- Bot displays specific account data

**NEVER select "None of these" if there's an option that matches the customer's intent!**

Respond in this exact JSON format:
{{
    "action": "<CLICK_MENU|CONTINUE|PASS|FAIL>",
    "menu_choice": "<exact menu text to click, or empty>",
    "follow_up": "<text to type if CONTINUE, or empty>",
    "reason": "<brief explanation>",
    "score": <1-10 quality rating>,
    "intent_identified": <true if bot understood what user wanted>,
    "flow_completed": <true if bot completed the task>
}}
"""




def analyze_and_decide(
    utterance: str,
    bot_response: str,
    menu_options: list[str] = None,
    action_history: list[dict] = None,
    max_retries: int = 3
) -> AdaptiveDecision:
    """
    Analyze bot response and decide next action for adaptive testing.
    
    Args:
        utterance: The user's message/question
        bot_response: The bot's response text
        menu_options: List of available menu button texts
        action_history: List of previous actions taken (for loop detection)
        max_retries: Number of retries on API failure
    
    Returns:
        AdaptiveDecision with action, menu_choice/follow_up, and scores
    """
    if not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY not set. Using fallback decision.")
        return _create_fallback_decision(utterance, bot_response)
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            generation_config = genai.types.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                max_output_tokens=LLM_MAX_TOKENS,
            )
            
            # Format menu options
            menu_str = "\n".join(f"- {opt}" for opt in (menu_options or [])) or "No menu options available"
            
            # Format action history for context
            if action_history:
                history_lines = []
                for h in action_history[-5:]:  # Last 5 actions for context
                    action_taken = h.get('action', 'UNKNOWN')
                    menu_clicked = h.get('menu_choice', '') or h.get('reason', '')[:40]
                    history_lines.append(f"- Turn {h.get('turn', '?')}: {action_taken} - {menu_clicked}")
                history_str = "\n".join(history_lines) if history_lines else "No previous actions"
            else:
                history_str = "No previous actions (this is the first turn)"
            
            prompt = ADAPTIVE_PROMPT.format(
                utterance=utterance,
                bot_response=bot_response if bot_response else "[No response received]",
                menu_options=menu_str,
                action_history=history_str
            )
            
            response = model.generate_content(prompt, generation_config=generation_config)
            response_text = response.text.strip()
            
            # Extract JSON from response (handles markdown code blocks)
            try:
                data = extract_json_from_response(response_text)
                
                return AdaptiveDecision(
                    action=data.get("action", "FAIL").upper(),
                    menu_choice=data.get("menu_choice", ""),
                    follow_up=data.get("follow_up", ""),
                    reason=data.get("reason", ""),
                    score=float(data.get("score", 0)),
                    intent_identified=data.get("intent_identified", False),
                    flow_completed=data.get("flow_completed", False)
                )
            except ValueError as e:
                print(f"[Attempt {attempt+1}] {e}")
                last_error = str(e)
            
        except json.JSONDecodeError as e:
            print(f"[Attempt {attempt+1}] JSON parse error: {e}")
            last_error = str(e)
        except Exception as e:
            print(f"[Attempt {attempt+1}] LLM error: {type(e).__name__}: {e}")
            last_error = str(e)
            
            # Wait before retry (exponential backoff)
            if attempt < max_retries - 1:
                import time
                wait_time = (2 ** attempt) * 0.5  # 0.5s, 1s, 2s
                print(f"  Retrying in {wait_time}s...")
                time.sleep(wait_time)
    
    print(f"LLM adaptive decision failed after {max_retries} attempts: {last_error}")
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

