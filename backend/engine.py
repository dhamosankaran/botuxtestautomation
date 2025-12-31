"""Playwright automation engine for Citi chatbot testing."""
import time
import os
import json
from datetime import datetime
from typing import List, Optional
from playwright.sync_api import sync_playwright, Page, Browser
from sqlmodel import Session
from dotenv import load_dotenv

load_dotenv()

from database import engine
from models import TestRun, ConversationLog, Credentials, ChatbotConfig, LoginSelectors, get_local_now
from llm_evaluator import evaluate_response, EvaluationResult, analyze_and_decide, AdaptiveDecision, analyze_screenshot_with_vision
from utterances import get_category_for_utterance, get_expected_intent

# Playwright configuration from environment
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
PLAYWRIGHT_SLOW_MO = int(os.getenv("PLAYWRIGHT_SLOW_MO", "200"))
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "60000"))
print(f"[ENGINE CONFIG] Headless={PLAYWRIGHT_HEADLESS}, SlowMo={PLAYWRIGHT_SLOW_MO}ms, Timeout={PLAYWRIGHT_TIMEOUT}ms")

# Citi credentials from .env (fallback if not provided in request)
CITI_USER_ID = os.getenv("CITI_USER_ID", "")
CITI_PASSWORD = os.getenv("CITI_PASSWORD", "")

# Screenshot configuration
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
CAPTURE_SCREENSHOTS = os.getenv("CAPTURE_SCREENSHOTS", "true").lower() == "true"


def capture_screenshot(
    page: Page,
    test_run_id: int,
    utterance: str,
    status: str,
    suffix: str = ""
) -> str:
    """
    Capture a screenshot, especially on failures.
    
    Args:
        page: Playwright page object
        test_run_id: Test run ID for organization
        utterance: The utterance being tested
        status: Test status (pass/fail)
        suffix: Optional suffix for filename
    
    Returns:
        Path to saved screenshot, or empty string if not captured
    """
    if not CAPTURE_SCREENSHOTS:
        return ""
    
    # Capture on failures, debug mode, or when suffix is provided
    if status == "pass" and not suffix:
        return ""
    
    try:
        # Create directory for this test run
        run_dir = os.path.join(SCREENSHOTS_DIR, f"run_{test_run_id}")
        os.makedirs(run_dir, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%H%M%S")
        # Clean utterance for filename
        clean_utterance = "".join(c if c.isalnum() else "_" for c in utterance[:30])
        suffix_str = f"_{suffix}" if suffix else ""
        filename = f"{timestamp}_{status}_{clean_utterance}{suffix_str}.png"
        
        filepath = os.path.join(run_dir, filename)
        
        # Capture screenshot
        page.screenshot(path=filepath, full_page=True)
        print(f"📸 Screenshot saved: {filepath}")
        
        return filepath
        
    except Exception as e:
        print(f"Warning: Failed to capture screenshot: {e}")
        return ""


def get_screenshots_for_run(test_run_id: int) -> List[str]:
    """
    Get all screenshots for a test run.
    
    Args:
        test_run_id: Test run ID
    
    Returns:
        List of screenshot file paths
    """
    run_dir = os.path.join(SCREENSHOTS_DIR, f"run_{test_run_id}")
    if not os.path.exists(run_dir):
        return []
    
    screenshots = []
    for filename in sorted(os.listdir(run_dir)):
        if filename.endswith(".png"):
            screenshots.append(os.path.join(run_dir, filename))
    
    return screenshots

# Helper function to detect invalid bot responses
import re

# Invalid response patterns - these are not actual bot content
INVALID_RESPONSE_PATTERNS = [
    # Typing/loading indicators
    r".*is typing.*",
    r".*loading.*",
    r".*please wait.*",
    r".*one moment.*",
    r".*thinking.*",
    # Timestamps only
    r"^\d{1,2}:\d{2}(\s*[APap][Mm])?$",
    # Empty or placeholder text
    r"^\.\.\.$",
    r"^…$",
]

# Compiled patterns for efficiency
INVALID_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in INVALID_RESPONSE_PATTERNS]

# Keywords that indicate an invalid/incomplete response
INVALID_RESPONSE_KEYWORDS = [
    "is typing",
    "loading",
    "please wait",
    "one moment",
    "processing",
    "connecting",
]


def is_invalid_response(text: str) -> bool:
    """
    Check if the text is an invalid bot response (typing indicator, timestamp, loading state).
    Returns True if the response should be filtered out.
    """
    if not text:
        return True
    
    text = text.strip()
    
    # Too short responses
    if len(text) < 5:
        return True
    
    # Check against invalid patterns
    for pattern in INVALID_PATTERNS_COMPILED:
        if pattern.match(text):
            return True
    
    # Check against invalid keywords
    text_lower = text.lower()
    for keyword in INVALID_RESPONSE_KEYWORDS:
        if keyword in text_lower:
            return True
    
    # Check if it's just a timestamp (short text with time format)
    if len(text) < 15:
        time_pattern = r'^\d{1,2}:\d{2}(\s*[APap][Mm])?$'
        if re.match(time_pattern, text):
            return True
    
    return False


def is_valid_balance_response(response: str) -> bool:
    """
    Check if the response contains meaningful balance information.
    Used for enhanced success criteria validation.
    """
    if not response:
        return False
    
    response_lower = response.lower()
    
    # Check for monetary amounts
    has_amount = bool(re.search(r'\$[\d,]+\.?\d*', response))
    
    # Check for account-related keywords
    account_keywords = ['balance', 'account', 'card', 'available', 'credit', 'checking', 'savings']
    has_account_ref = any(kw in response_lower for kw in account_keywords)
    
    # Check for actionable information (menu options count as valid)
    action_keywords = ['go to', 'view', 'see', 'check', 'select', 'click']
    has_action = any(kw in response_lower for kw in action_keywords)
    
    return has_amount or (has_account_ref and has_action) or has_account_ref


def get_response_quality_score(response: str, category: str) -> float:
    """
    Get a quality score (0-10) for a response based on content analysis.
    Used when LLM evaluation is unavailable.
    """
    if not response or is_invalid_response(response):
        return 0.0
    
    score = 5.0  # Base score for having a response
    
    # Category-specific scoring
    if category == "account_balance":
        if is_valid_balance_response(response):
            score += 3.0
        if re.search(r'\$[\d,]+', response):
            score += 2.0
    elif category in ["transactions", "payments"]:
        if any(kw in response.lower() for kw in ['transaction', 'payment', 'amount', 'date']):
            score += 3.0
    elif category == "card_issues":
        if any(kw in response.lower() for kw in ['card', 'lock', 'report', 'replace']):
            score += 3.0
    
    return min(score, 10.0)


# Keywords that indicate escalation to human support
ESCALATION_KEYWORDS = [
    "call support", "contact support", "speak to agent",
    "human agent", "live agent", "phone number",
    "call us at", "representative", "transfer",
    "speak with", "talk to a", "customer service",
    "1-800", "1-888", "1-877", "toll free"
]


def detect_escalation(response: str) -> bool:
    """Check if bot response contains escalation keywords."""
    response_lower = response.lower()
    return any(keyword in response_lower for keyword in ESCALATION_KEYWORDS)


# Patterns for text that should be filtered out (menu buttons, not actual bot messages)
BUTTON_TEXT_PATTERNS = [
    r"^my credit card$",
    r"^my atm.*debit card$",
    r"^my banking account$",
    r"^yes$",
    r"^no$",
    r"^confirm$",
    r"^cancel$",
    r"^continue$",
    r"^done$",
    r"^ok$",
    r"^okay$",
    r"^go to",
    r"^view account",
    r"^see more",
    r"^request cash advance",
    r"^atm.*branch locator",
    r"card\.{3}\d{4}$",  # "Card...1234" pattern
    r"checking\.{3}\d{4}$",
    r"savings\.{3}\d{4}$",
    r"account isn.t listed",
]


def is_button_text(text: str) -> bool:
    """Check if the text looks like a button label rather than bot message."""
    if not text:
        return False
    text_lower = text.lower().strip()
    for pattern in BUTTON_TEXT_PATTERNS:
        if re.match(pattern, text_lower, re.IGNORECASE):
            return True
    return False


def extract_bot_narrative_text(page: Page) -> str:
    """
    Extract ONLY narrative/conversational text from bot messages.
    Excludes button labels, menu options, and clickable elements.
    
    Uses JavaScript DOM traversal to walk through text nodes and 
    filter out those that belong to clickable elements.
    
    Args:
        page: Playwright page object
        
    Returns:
        The narrative text from the bot's response
    """
    try:
        result = page.evaluate("""
            () => {
                // Find the most recent bot message container
                const botMessageSelectors = [
                    '[class*="bot-message"]',
                    '[class*="assistant-message"]',
                    '[class*="from-bot"]',
                    '[class*="incoming-message"]',
                    '[class*="chat-message"]:not([class*="user"])',
                    '[class*="message-bubble"]:not([class*="user"])'
                ];
                
                let latestBotMessage = null;
                for (const selector of botMessageSelectors) {
                    const elements = document.querySelectorAll(selector);
                    if (elements.length > 0) {
                        latestBotMessage = elements[elements.length - 1];
                        break;
                    }
                }
                
                if (!latestBotMessage) {
                    // Fallback: look in chat container for last non-user message
                    const chatContainer = document.querySelector(
                        '[class*="chat-widget"], [class*="chat-container"], [class*="messaging"]'
                    );
                    if (chatContainer) {
                        const allMessages = chatContainer.querySelectorAll('[class*="message"]');
                        for (let i = allMessages.length - 1; i >= 0; i--) {
                            const msg = allMessages[i];
                            const classes = msg.className.toLowerCase();
                            if (!classes.includes('user') && !classes.includes('outgoing')) {
                                latestBotMessage = msg;
                                break;
                            }
                        }
                    }
                }
                
                if (!latestBotMessage) {
                    return { narrative: '', buttonLabels: [], found: false };
                }
                
                // Patterns for clickable elements to skip
                const clickableSelectors = 'button, [role="button"], a, [onclick], [tabindex="0"], [class*="chip"], [class*="option"], [class*="selection"]';
                
                // Patterns for button-like text to filter
                const buttonPatterns = [
                    /^my credit card$/i,
                    /^my atm.*debit card$/i,
                    /^my banking account$/i,
                    /^yes$/i, /^no$/i,
                    /^confirm$/i, /^cancel$/i,
                    /^continue$/i, /^done$/i,
                    /^ok$/i, /^okay$/i,
                    /^go to/i, /^view account/i,
                    /^see more/i, /^request cash/i,
                    /card\\.{3}\\d{4}$/i,
                    /checking\\.{3}\\d{4}$/i,
                    /savings\\.{3}\\d{4}$/i,
                    /account isn.t listed/i,
                    /^sign off$/i, /^sign on$/i
                ];
                
                const narrativeTexts = [];
                const buttonLabels = [];
                
                // Walk through all text nodes
                const walker = document.createTreeWalker(
                    latestBotMessage,
                    NodeFilter.SHOW_TEXT,
                    null,
                    false
                );
                
                while (walker.nextNode()) {
                    const textNode = walker.currentNode;
                    const text = textNode.textContent.trim();
                    
                    if (!text || text.length < 2) continue;
                    
                    // Check if this text node is inside a clickable element
                    let parent = textNode.parentElement;
                    let isClickable = false;
                    while (parent && parent !== latestBotMessage) {
                        if (parent.matches && parent.matches(clickableSelectors)) {
                            isClickable = true;
                            break;
                        }
                        parent = parent.parentElement;
                    }
                    
                    // Check if text matches button patterns
                    const isButtonText = buttonPatterns.some(p => p.test(text));
                    
                    if (isClickable || isButtonText) {
                        buttonLabels.push(text);
                    } else {
                        narrativeTexts.push(text);
                    }
                }
                
                // Join narrative texts, filtering duplicates
                const seen = new Set();
                const uniqueNarrative = narrativeTexts.filter(t => {
                    if (seen.has(t.toLowerCase())) return false;
                    seen.add(t.toLowerCase());
                    return true;
                });
                
                return {
                    narrative: uniqueNarrative.join(' ').trim(),
                    buttonLabels: buttonLabels,
                    found: true
                };
            }
        """)
        
        if result and result.get('found'):
            narrative = result.get('narrative', '')
            buttons = result.get('buttonLabels', [])
            if buttons:
                print(f"[BotNarrative] Filtered out button text: {buttons[:3]}")
            if narrative:
                print(f"[BotNarrative] Extracted: {narrative[:80]}...")
            return narrative
        return ""
        
    except Exception as e:
        print(f"[BotNarrative] Error extracting narrative: {e}")
        return ""


def filter_button_text_from_response(raw_response: str) -> str:
    """
    Filter out button/menu text from a raw response string.
    This is a fallback when JavaScript DOM traversal isn't possible.
    
    Args:
        raw_response: Raw text that may contain button labels
        
    Returns:
        Cleaned text with button labels removed
    """
    if not raw_response:
        return ""
    
    # Split by common separators and filter each part
    parts = re.split(r'\s{2,}|\n', raw_response)
    filtered = []
    
    for part in parts:
        part = part.strip()
        if part and not is_button_text(part):
            filtered.append(part)
    
    # If everything was filtered, return original (better than nothing)
    if not filtered:
        return raw_response
    
    return ' '.join(filtered)

def wait_for_stable_response(page: Page, timeout_ms: int = 10000, check_interval_ms: int = 500) -> str:
    """
    Wait for bot response to stabilize (no changes for 500ms).
    This helps ensure we capture the final response, not intermediate states.
    
    ENHANCED: Now uses extract_bot_narrative_text to filter out button labels
    and capture only the actual bot message content.
    
    Args:
        page: Playwright page object
        timeout_ms: Maximum time to wait in milliseconds
        check_interval_ms: Interval between stability checks
        
    Returns:
        Stable bot response text or empty string
    """
    response_selectors = [
        "[class*='message-content']",
        "[class*='chat-message']",
        "[class*='bot-message']",
        "[class*='assistant-message']",
        "[class*='bubble']",
        "[class*='response']",
        "[class*='message']:not([class*='user'])",
    ]
    
    last_response = ""
    stable_count = 0
    required_stable_checks = 2  # Response must be the same for 2 consecutive checks
    
    elapsed = 0
    while elapsed < timeout_ms:
        current_response = ""
        
        # FIRST: Try to extract clean narrative text using DOM traversal
        try:
            narrative = extract_bot_narrative_text(page)
            if narrative and len(narrative) > 15 and not is_invalid_response(narrative):
                current_response = narrative
        except Exception as e:
            print(f"[StableResponse] Narrative extraction failed: {e}")
        
        # FALLBACK: Use selector-based approach if narrative is empty
        if not current_response:
            for selector in response_selectors:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        latest = elements[-1]
                        raw_text = (latest.text_content() or "").strip()
                        if raw_text and len(raw_text) > 10:
                            # Filter out button text from raw response
                            filtered = filter_button_text_from_response(raw_text)
                            if filtered and len(filtered) > 10 and not is_invalid_response(filtered):
                                current_response = filtered
                                break
                except Exception:
                    continue
        
        # Check if response is stable
        if current_response and current_response == last_response:
            stable_count += 1
            if stable_count >= required_stable_checks:
                print(f"[StableResponse] Stable after {elapsed}ms: {current_response[:60]}...")
                return current_response
        else:
            stable_count = 0
            last_response = current_response
        
        page.wait_for_timeout(check_interval_ms)
        elapsed += check_interval_ms
    
    if last_response:
        print(f"[StableResponse] Timeout, returning last: {last_response[:60]}...")
    return last_response if last_response else ""


def run_citi_chatbot_test(
    test_run_id: int,
    target_url: str,
    utterances: List[str],
    credentials: Optional[Credentials] = None,
    chatbot_config: Optional[ChatbotConfig] = None
):
    """
    Run the Citi chatbot test using Playwright.
    
    This function is designed to be called from FastAPI BackgroundTasks.
    It handles:
    1. Login to Citi.com
    2. Navigate to dashboard and open chat widget
    3. Send test utterances and capture responses
    4. Evaluate responses with LLM
    5. Store results in database
    """
    import sys
    print(f"[DEBUG] run_citi_chatbot_test started! test_run_id={test_run_id}", flush=True)
    sys.stdout.flush()
    
    # Default config for Citi if not provided
    if chatbot_config is None:
        chatbot_config = ChatbotConfig()
    
    context = None  # Will be set in try block
    
    try:
        with sync_playwright() as p:
            # Use REAL Chrome browser (not Chromium) with persistent profile
            # This uses the user's actual Chrome installation which is less likely to be detected as a bot
            user_data_dir = "/tmp/citi_browser_profile"
            
            print("Launching Chrome browser (using your installed Chrome)...")
            # Clean desktop browser settings - 1680x1050 common resolution
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                channel="chrome",
                headless=PLAYWRIGHT_HEADLESS,
                slow_mo=PLAYWRIGHT_SLOW_MO,
                viewport={"width": 1680, "height": 1050},  # Common desktop resolution
                locale="en-US",
                timezone_id="America/Chicago",
                color_scheme="light",
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                ]
            )
            
            # Get or create page
            page = context.pages[0] if context.pages else context.new_page()
            
            # Step 1: Navigate to Citi.com
            print(f"Navigating to {target_url}")
            page.goto(target_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)
            page.wait_for_timeout(3000)
            
            # Step 2: Login handling
            # Check if credentials provided, otherwise wait for manual login
            login_creds = credentials
            if not login_creds or not login_creds.username or not login_creds.password:
                if CITI_USER_ID and CITI_PASSWORD:
                    print("Using credentials from .env file (CITI_USER_ID, CITI_PASSWORD)")
                    login_creds = Credentials(username=CITI_USER_ID, password=CITI_PASSWORD)
                else:
                    login_creds = None
            
            if login_creds and login_creds.username and login_creds.password:
                # Automated login
                perform_citi_login(page, login_creds)
            else:
                # Manual login mode - wait for user to login
                print("=" * 50)
                print("MANUAL LOGIN MODE")
                print("Please login manually in the browser window.")
                print("Waiting for dashboard to load...")
                print("=" * 50)
                
                wait_for_manual_login(page)
            
            # Step 3: Wait for dashboard and find chat widget
            wait_for_dashboard_and_open_chat(page)
            
            # Step 4: Process each utterance with ADAPTIVE testing (LLM-driven menu clicking)
            latencies = []
            quality_scores = []
            
            print("\n" + "="*60)
            print("STARTING ADAPTIVE TESTING MODE")
            print("LLM will analyze responses and click menu options as needed")
            print("="*60)
            
            with Session(engine) as session:
                for utterance in utterances:
                    # Use adaptive test with LLM-driven conversation flow
                    result = run_adaptive_test(
                        page, utterance, test_run_id, session, max_turns=5
                    )
                    if result:
                        latencies.append(result.get("latency", 0))
                        if result.get("quality_score"):
                            quality_scores.append(result["quality_score"])
                
                # Calculate and save final metrics
                update_test_run_metrics(session, test_run_id, latencies, quality_scores)
            
            context.close()
            
    except Exception as e:
        print(f"Test failed with error: {e}")
        # Mark test as failed
        with Session(engine) as session:
            test_run = session.get(TestRun, test_run_id)
            if test_run:
                test_run.status = "failed"
                test_run.completed_at = get_local_now()
                test_run.error_message = str(e)
                session.add(test_run)
                session.commit()
        
        try:
            context.close()
        except Exception:
            pass
        raise


def wait_for_manual_login(page: Page, timeout_seconds: int = 120):
    """
    Wait for user to manually login.
    Polls the URL to detect when dashboard has loaded.
    """
    print(f"Waiting up to {timeout_seconds} seconds for manual login...")
    
    dashboard_indicators = ["dashboard", "summary", "accounts", "ag/", "myaccounts"]
    
    for second in range(timeout_seconds):
        page.wait_for_timeout(1000)  # Wait 1 second
        
        current_url = page.url.lower()
        
        # Check if we've navigated to a dashboard page
        if any(indicator in current_url for indicator in dashboard_indicators):
            print(f"Dashboard detected at: {page.url}")
            print("Manual login successful!")
            
            # Wait for page to fully load
            print("Waiting 10 seconds for dashboard to fully load...")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            
            page.wait_for_timeout(3000)  # 3 second wait for dashboard to load (reduced from 10s)
            print("Dashboard ready - proceeding with chat widget...")
            return True
        
        # Log progress every 10 seconds
        if second > 0 and second % 10 == 0:
            print(f"Still waiting... ({second}s elapsed)")
    
    raise Exception(f"Manual login timeout after {timeout_seconds} seconds - dashboard not detected")


def perform_citi_login(page: Page, credentials: Credentials):
    """Perform login on Citi.com with improved stability for Angular CDK form fields."""
    print("Performing Citi login...")
    
    try:
        # Wait for page to stabilize - use domcontentloaded (faster, won't timeout)
        print("Waiting for page to stabilize...")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            print("DOM load wait timed out, continuing anyway...")
        page.wait_for_timeout(3000)
        
        # Try to dismiss any notification banners that cause layout shifts
        try:
            close_buttons = page.query_selector_all("[class*='close'], [class*='dismiss'], button[aria-label*='close']")
            for btn in close_buttons:
                if btn.is_visible():
                    try:
                        btn.click(force=True)
                        print("Dismissed a notification banner")
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
        except Exception:
            pass
        
        # Wait specifically for the username field to be ready
        print("Waiting for login form...")
        try:
            page.wait_for_selector("#username", state="visible", timeout=10000)
        except Exception:
            print("Username field not found with #username, trying alternatives...")
        
        page.wait_for_timeout(2000)  # Extra stabilization time for Angular components
        
        # --- Helper function to safely interact with Angular CDK form fields ---
        def safe_fill_field(field_locator, value: str, field_name: str):
            """Fill a field safely, handling Angular CDK form-field wrapper interception."""
            
            def verify_fill(expected_value):
                """Check if the field contains the expected value."""
                try:
                    actual = field_locator.first.input_value()
                    if actual == expected_value:
                        print(f"Verified {field_name}: value correctly set")
                        return True
                    else:
                        print(f"Verification failed for {field_name}: expected '{expected_value[:3]}...' got '{actual[:20] if actual else 'empty'}'")
                        return False
                except Exception:
                    return False
            
            try:
                if field_locator.count() > 0:
                    print(f"Found {field_name} field, attempting to fill...")
                    
                    # Clear field first
                    try:
                        field_locator.first.fill("")
                    except Exception:
                        pass
                    
                    # Method 1: Try direct fill (bypasses click interception)
                    try:
                        field_locator.first.fill(value, timeout=5000)
                        print(f"Filled {field_name} using direct fill")
                        if verify_fill(value):
                            return True
                    except Exception as e1:
                        print(f"Direct fill failed: {e1}")
                    
                    # Method 2: Try force click then type character by character
                    try:
                        field_locator.first.click(force=True, timeout=5000)
                        page.wait_for_timeout(300)
                        # Clear and type
                        field_locator.first.fill("")
                        field_locator.first.type(value, delay=50)  # Type slowly
                        print(f"Filled {field_name} using force click + type")
                        if verify_fill(value):
                            return True
                    except Exception as e2:
                        print(f"Force click + type failed: {e2}")
                    
                    # Method 3: Use JavaScript to focus and set value (handles special chars)
                    try:
                        # Pass value as argument to avoid escaping issues
                        field_locator.first.evaluate(
                            "(el, val) => { el.focus(); el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }",
                            value
                        )
                        print(f"Filled {field_name} using JavaScript")
                        if verify_fill(value):
                            return True
                    except Exception as e3:
                        print(f"JavaScript fill failed: {e3}")
                    
                    # Final check
                    print(f"WARNING: All fill methods attempted for {field_name}")
                    return verify_fill(value)
                    
                else:
                    print(f"ERROR: {field_name} field locator found 0 elements")
                    return False
            except Exception as e:
                print(f"Error filling {field_name}: {e}")
                return False
        
        # --- Helper function for safe button click ---
        def safe_click_button(btn_locator, button_name: str):
            """Click a button safely with force option and JS fallback."""
            try:
                if btn_locator.count() > 0:
                    # Method 1: Force click
                    try:
                        btn_locator.first.click(force=True, timeout=5000)
                        print(f"Clicked {button_name} using force click")
                        return True
                    except Exception:
                        pass
                    
                    # Method 2: JavaScript click
                    try:
                        btn_locator.first.evaluate("el => el.click()")
                        print(f"Clicked {button_name} using JavaScript")
                        return True
                    except Exception:
                        pass
                    
                return False
            except Exception:
                return False
        
        # Use locator API targeting the actual input elements
        username_field = page.locator("#username")
        password_field = page.locator("#password")
        
        # Fill username
        username_filled = safe_fill_field(username_field, credentials.username, "username")
        if not username_filled:
            # Fallback to other selectors
            for selector in ["input[name='username']", "#userId", "input[type='text']:first-of-type"]:
                try:
                    field = page.locator(selector)
                    if safe_fill_field(field, credentials.username, f"username ({selector})"):
                        break
                except Exception:
                    continue
        
        page.wait_for_timeout(500)
        
        # Fill password
        password_filled = safe_fill_field(password_field, credentials.password, "password")
        if not password_filled:
            # Fallback
            try:
                field = page.locator("input[type='password']")
                safe_fill_field(field, credentials.password, "password (fallback)")
            except Exception:
                print("Warning: Could not find password field")
        
        page.wait_for_timeout(500)
        
        # Click Sign On button
        sign_on_btn = page.locator("#signInBtn")
        if not safe_click_button(sign_on_btn, "Sign On"):
            # Fallback: try text-based button
            try:
                sign_on_role = page.get_by_role("button", name="Sign On")
                if not safe_click_button(sign_on_role, "Sign On (role)"):
                    # Last resort: press Enter
                    page.keyboard.press("Enter")
                    print("Pressed Enter to submit")
            except Exception:
                page.keyboard.press("Enter")
                print("Pressed Enter to submit (fallback)")
        
        # Wait for navigation after login
        print("Waiting for login navigation...")
        
        # Method 1: Wait for URL to change from login page
        initial_url = page.url
        print(f"Initial URL: {initial_url}")
        
        for attempt in range(30):  # Wait up to 30 seconds
            page.wait_for_timeout(1000)
            try:
                current = page.url.lower()
                # Check if URL changed and we're on a dashboard/account page
                if current != initial_url.lower():
                    print(f"URL changed to: {page.url}")
                    if "dashboard" in current or "summary" in current or "accounts" in current or "ag/" in current:
                        print("Detected dashboard redirect - login successful!")
                        break
                    elif "security" in current or "verify" in current or "challenge" in current:
                        print("Detected security challenge page")
                        break
                    elif "login" not in current:
                        # Some other page, might be loading
                        print(f"Navigated to different page, continuing...")
                # Check for error messages while on page
                page_content = page.content().lower()
                if "invalid" in page_content and "user id" in page_content:
                    print("Detected login error on page")
                    break
            except Exception as e:
                print(f"Navigation check error: {e}")
                break
        
        # Final wait for page to stabilize
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
            print("Page reached networkidle state")
        except Exception:
            print("Networkidle timeout - continuing anyway")
        
        # Check result and save screenshot for debugging
        current_url = page.url.lower()
        print(f"Final URL after login attempt: {page.url}")
        
        # Try to save a screenshot for debugging
        try:
            screenshot_path = "/tmp/citi_login_debug.png"
            page.screenshot(path=screenshot_path)
            print(f"Screenshot saved to: {screenshot_path}")
        except Exception as e:
            print(f"Could not save screenshot: {e}")
        
        # Detect various login states - BE STRICT
        page_content = page.content().lower()
        
        if "dashboard" in current_url or "summary" in current_url or "ag/" in current_url or "accounts" in current_url:
            print(f"Login successful! Redirected to dashboard")
            return True  # Success!
        elif "security" in current_url or "verify" in current_url or "challenge" in current_url:
            print("Security challenge detected - may need 2FA")
            # Wait a bit more for manual intervention if needed
            page.wait_for_timeout(3000)
            # Check again after waiting
            if "dashboard" in page.url.lower() or "accounts" in page.url.lower():
                return True
            raise Exception("Login failed - stuck at security challenge (2FA required?)")
        elif "error" in current_url:
            print("Login appears to have failed - error in URL")
            raise Exception("Login failed - error page detected in URL")
        elif any(msg in page_content for msg in ["invalid user id or password", "incorrect password", "login failed", "unable to sign", "enter a valid password"]):
            print("Login appears to have failed - error message detected on page")
            raise Exception("Login failed - invalid credentials detected on page")
        elif "login" in current_url or "#" in page.url:
            # Still on login page - this is a FAILURE
            print("Still on login page - login did NOT complete successfully")
            raise Exception("Login failed - still on login page after credentials submitted")
        else:
            print(f"Unknown login state - URL: {page.url}")
            raise Exception(f"Login failed - unknown state, URL: {page.url}")
            
    except Exception as e:
        print(f"Login error: {e}")
        raise


def wait_for_dashboard_and_open_chat(page: Page):
    """
    Wait for dashboard to load and open the Citi Bot widget via Search panel.
    
    5-Step Flow (Updated based on actual UI):
    1. Verify dashboard is showing with account details
    2. Click magnifying glass (Search icon) in header next to "Sign Off"
    3. Scroll to "Let's Chat!" section and click "Ask Citi® Bot" button
    4. Wait for "Welcome to Chat with Citi" dialog and click "Get started"
    5. Wait for chat interface with "Write a message..." input field
    """
    print("=" * 60)
    print("OPENING CITIBOT VIA SEARCH PANEL - LET'S CHAT METHOD")
    print("=" * 60)
    
    # ========== STEP 1: Verify Dashboard is Showing ==========
    print("\n[STEP 1] Verifying dashboard is showing with account details...")
    
    # Wait for dashboard to load
    page.wait_for_timeout(3000)
    
    # Check for dashboard indicators
    dashboard_indicators = [
        "text=Good Morning",
        "text=Good Afternoon", 
        "text=Good Evening",
        "text=ACCOUNT OVERVIEW",
        "text=Citi Summary",
        "text=BANKING",
        "text=Net Worth",
    ]
    
    dashboard_found = False
    for indicator in dashboard_indicators:
        try:
            if page.locator(indicator).first.is_visible(timeout=2000):
                print(f"Dashboard verified: found '{indicator}'")
                dashboard_found = True
                break
        except Exception:
            continue
    
    if not dashboard_found:
        print("Dashboard indicators not found, but proceeding anyway...")
    
    # Take dashboard screenshot
    try:
        page.screenshot(path="/tmp/citi_step1_dashboard.png")
        print("Step 1 screenshot saved")
    except Exception:
        pass
    
    # ========== STEP 2: Click Search Icon (Magnifying Glass) "How can we help?" ==========
    print("\n[STEP 2] Clicking Search icon (magnifying glass) 'How can we help?' in top right...")
    
    search_clicked = False
    
    # Primary selectors for the "How can we help?" magnifying glass icon
    # This is in the top right corner, NOT the Profile button
    search_icon_selectors = [
        # Direct text-based selectors for "How can we help?"
        "text=How can we help",
        ":text('How can we help')",
        "[aria-label*='How can we help' i]",
        
        # Search-specific aria labels
        "[aria-label*='search' i]:not([aria-label*='profile' i])",
        "button[aria-label*='search' i]",
        "a[aria-label*='search' i]",
        
        # Look for magnifying glass icon by class
        "[class*='search-icon']",
        "[class*='searchIcon']",
        "[class*='search'] svg",
        
        # SVG buttons in utility/header area that are NOT profile
        "[class*='utility'] button:has(svg):not(:has-text('Profile'))",
    ]
    
    for selector in search_icon_selectors:
        if search_clicked:
            break
        try:
            elements = page.locator(selector)
            count = elements.count()
            if count > 0:
                print(f"Trying selector '{selector}' ({count} elements)")
            for i in range(min(count, 3)):
                try:
                    el = elements.nth(i)
                    if el.is_visible(timeout=1500):
                        text = (el.text_content() or "").lower()
                        # Skip if it contains "profile" or "sign off"
                        if "profile" in text or "sign off" in text:
                            continue
                        box = el.bounding_box()
                        if box:
                            print(f"Clicking search icon: {selector}[{i}]")
                            el.click(force=True)
                            search_clicked = True
                            break
                except Exception:
                    continue
        except Exception:
            continue
    
    # JavaScript fallback - specifically look for "How can we help" or search icon
    if not search_clicked:
        print("Trying JavaScript to find 'How can we help' search icon...")
        try:
            result = page.evaluate("""
                () => {
                    // First try to find "How can we help" text or related element
                    const howCanWeHelp = document.evaluate(
                        "//*[contains(text(), 'How can we help')]",
                        document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
                    ).singleNodeValue;
                    if (howCanWeHelp) {
                        howCanWeHelp.click();
                        return 'clicked How can we help';
                    }
                    
                    // Look for search aria-label, avoiding profile
                    const searchByAria = document.querySelector('[aria-label*="search" i]:not([aria-label*="profile" i])');
                    if (searchByAria) {
                        searchByAria.click();
                        return 'clicked by aria-label';
                    }
                    
                    // Look for magnifying glass SVG in header, avoiding profile buttons
                    const header = document.querySelector('header, nav, [class*="header"]');
                    if (header) {
                        const buttons = header.querySelectorAll('button, a');
                        for (const btn of buttons) {
                            const text = btn.textContent?.toLowerCase() || '';
                            const label = btn.getAttribute('aria-label')?.toLowerCase() || '';
                            // Skip profile-related buttons
                            if (text.includes('profile') || label.includes('profile') || 
                                text.includes('sign off') || label.includes('sign off')) {
                                continue;
                            }
                            // Click if it has search-related attributes or SVG
                            if (label.includes('search') || text.includes('help') || 
                                btn.querySelector('svg')) {
                                btn.click();
                                return 'clicked header button';
                            }
                        }
                    }
                    
                    return null;
                }
            """)
            if result:
                print(f"JavaScript click: {result}")
                search_clicked = True
        except Exception as e:
            print(f"JavaScript search click failed: {e}")
    
    if not search_clicked:
        print("WARNING: Could not click Search icon!")
    
    # ========== STEP 3: Find "Let's Chat!" Section and Click "Ask Citi® Bot" ==========
    print("\n[STEP 3] Waiting for search panel, then finding 'Let's Chat!' section...")
    page.wait_for_timeout(3000)
    
    # Take screenshot of search panel
    try:
        page.screenshot(path="/tmp/citi_step3_search_panel.png")
        print("Step 3 screenshot saved")
    except Exception:
        pass
    
    # Scroll within the search panel to find "Let's Chat!" section
    print("Scrolling to find 'Let's Chat!' section...")
    
    # Try to find and scroll to "Let's Chat!" text
    lets_chat_found = False
    lets_chat_selectors = [
        "text=Let's Chat!",
        "text=Let's Chat",
        "[class*='chat']:has-text('Let\\'s Chat')",
        "h2:has-text('Let\\'s Chat')",
        "h3:has-text('Let\\'s Chat')",
        "[class*='panel']:has-text('Let\\'s Chat')",
    ]
    
    for selector in lets_chat_selectors:
        try:
            el = page.locator(selector).first
            if el.count() > 0:
                # Scroll element into view
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                print(f"Found 'Let's Chat!' section: {selector}")
                lets_chat_found = True
                break
        except Exception:
            continue
    
    # If not found via selectors, try JavaScript scroll
    if not lets_chat_found:
        print("Trying JavaScript to scroll to 'Let's Chat!' section...")
        try:
            page.evaluate("""
                () => {
                    // Find elements containing "Let's Chat"
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        if (el.textContent?.includes("Let's Chat") && el.offsetParent !== null) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            return true;
                        }
                    }
                    // If not found, scroll the panel to bottom
                    const panels = document.querySelectorAll('[class*="panel"], [class*="modal"], [class*="overlay"], [class*="search"]');
                    for (const panel of panels) {
                        if (panel.scrollHeight > panel.clientHeight) {
                            panel.scrollTop = panel.scrollHeight;
                        }
                    }
                    return false;
                }
            """)
            print("Scrolled via JavaScript")
        except Exception as e:
            print(f"JavaScript scroll failed: {e}")
    
    page.wait_for_timeout(2000)
    
    # Take screenshot after scrolling
    try:
        page.screenshot(path="/tmp/citi_step3b_lets_chat.png")
        print("Step 3b screenshot saved (after scroll)")
    except Exception:
        pass
    
    # Now click "Ask Citi® Bot" button
    print("Clicking 'Ask Citi® Bot' button...")
    ask_citibot_clicked = False
    
    ask_citibot_selectors = [
        "button:has-text('Ask Citi')",
        "text=Ask Citi® Bot",
        "text=Ask Citi Bot",
        "text=Ask CitiBot",
        "button:has-text('Ask CitiBot')",
        "[class*='citi']:has-text('Ask')",
        "a:has-text('Ask Citi')",
        "[role='button']:has-text('Ask Citi')",
    ]
    
    for selector in ask_citibot_selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                el.click(force=True)
                print(f"Clicked 'Ask Citi® Bot': {selector}")
                ask_citibot_clicked = True
                break
        except Exception:
            continue
    
    # JavaScript fallback for clicking Ask Citi Bot
    if not ask_citibot_clicked:
        print("Trying JavaScript to click 'Ask Citi® Bot'...")
        try:
            result = page.evaluate("""
                () => {
                    // Look for button/link containing "Ask Citi"
                    const buttons = document.querySelectorAll('button, a, [role="button"]');
                    for (const btn of buttons) {
                        const text = btn.textContent?.toLowerCase() || '';
                        if (text.includes('ask citi') || text.includes('citibot')) {
                            if (btn.offsetParent !== null) {
                                btn.click();
                                return 'clicked Ask Citi Bot button';
                            }
                        }
                    }
                    
                    // Also try any clickable element with citi bot text
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        const text = el.textContent?.toLowerCase() || '';
                        if ((text.includes('ask citi') || text.includes('citibot')) && 
                            el.offsetParent !== null &&
                            (el.tagName === 'BUTTON' || el.tagName === 'A' || 
                             el.getAttribute('role') === 'button' ||
                             el.onclick || el.style.cursor === 'pointer')) {
                            el.click();
                            return 'clicked Citi Bot element';
                        }
                    }
                    return null;
                }
            """)
            if result:
                print(f"JavaScript click: {result}")
                ask_citibot_clicked = True
        except Exception as e:
            print(f"JavaScript Ask Citi Bot click failed: {e}")
    
    if not ask_citibot_clicked:
        print("WARNING: Could not click 'Ask Citi® Bot' button!")
    
    # ========== STEP 4: Wait for Welcome Dialog and Click "Get started" ==========
    print("\n[STEP 4] Waiting for 'Welcome to Chat with Citi' dialog and clicking 'Get started'...")
    page.wait_for_timeout(2000)
    
    # Take screenshot of welcome dialog
    try:
        page.screenshot(path="/tmp/citi_step4_welcome_dialog.png")
        print("Step 4 screenshot saved (Welcome dialog)")
    except Exception:
        pass
    
    # Wait for and click "Get started" button
    get_started_clicked = False
    get_started_selectors = [
        "button:has-text('Get started')",
        "button:has-text('Get Started')",
        "text=Get started",
        "text=Get Started",
        "[class*='button']:has-text('Get started')",
        "a:has-text('Get started')",
        "[role='button']:has-text('Get started')",
    ]
    
    # Wait up to 10 seconds for Get started button
    for attempt in range(10):
        for selector in get_started_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=500):
                    el.click(force=True)
                    print(f"Clicked 'Get started' button: {selector}")
                    get_started_clicked = True
                    break
            except Exception:
                continue
        if get_started_clicked:
            break
        page.wait_for_timeout(1000)
        print(f"Waiting for 'Get started' button... ({attempt + 1}s)")
    
    # JavaScript fallback for Get started button
    if not get_started_clicked:
        print("Trying JavaScript to click 'Get started' button...")
        try:
            result = page.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button, a, [role="button"]');
                    for (const btn of buttons) {
                        const text = btn.textContent?.toLowerCase() || '';
                        if (text.includes('get started') || text === 'get started') {
                            if (btn.offsetParent !== null) {
                                btn.click();
                                return 'clicked Get started button';
                            }
                        }
                    }
                    return null;
                }
            """)
            if result:
                print(f"JavaScript click: {result}")
                get_started_clicked = True
        except Exception as e:
            print(f"JavaScript Get started click failed: {e}")
    
    if not get_started_clicked:
        print("WARNING: Could not click 'Get started' button!")
    
    # Wait for chat interface to load after clicking Get started
    print("Waiting for chat interface to load...")
    page.wait_for_timeout(3000)
    
    # ========== STEP 5: Scroll Chat Widget and Wait for Input Field ==========
    print("\n[STEP 5] Scrolling chat widget to show 'Write a message...' input...")
    
    # Scroll the chat widget to the bottom to make input field visible
    try:
        page.evaluate("""
            () => {
                // Find all potential chat containers and scroll to bottom
                const chatSelectors = [
                    '[class*="chat"]',
                    '[class*="Chat"]',
                    '[id*="chat"]',
                    '[class*="message-container"]',
                    '[class*="conversation"]',
                    '[class*="bot"]',
                    '[class*="Bot"]'
                ];
                
                for (const selector of chatSelectors) {
                    const containers = document.querySelectorAll(selector);
                    containers.forEach(container => {
                        if (container.scrollHeight > container.clientHeight) {
                            container.scrollTop = container.scrollHeight;
                        }
                    });
                }
                
                // Also try to scroll input into view if it exists
                const input = document.querySelector('input[placeholder*="message" i], textarea[placeholder*="message" i]');
                if (input) {
                    input.scrollIntoView({ behavior: 'instant', block: 'center' });
                }
                
                // Scroll the page/body to ensure chat widget is in view
                window.scrollTo(0, 0);
            }
        """)
        print("Scrolled chat widget to bottom")
    except Exception as e:
        print(f"Chat widget scroll failed: {e}")
    
    page.wait_for_timeout(1000)
    
    # Take screenshot
    try:
        page.screenshot(path="/tmp/citi_step5_chat_interface.png")
        print("Step 5 screenshot saved")
    except Exception:
        pass
    
    # Wait for the chat input field to appear
    chat_input_ready = False
    chat_input_selectors = [
        "input[placeholder*='Write a message' i]",
        "textarea[placeholder*='Write a message' i]",
        "input[placeholder*='message' i]",
        "textarea[placeholder*='message' i]",
        "[placeholder*='message' i]",
        "[class*='chat'] input",
        "[class*='chat'] textarea",
        "[class*='message-input']",
    ]
    
    # Wait up to 15 seconds for chat input to appear
    for attempt in range(15):
        for selector in chat_input_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=500):
                    print(f"Chat input found: {selector}")
                    chat_input_ready = True
                    break
            except Exception:
                continue
        if chat_input_ready:
            break
        page.wait_for_timeout(1000)
        print(f"Waiting for chat input... ({attempt + 1}s)")
    
    # Verify bot greeting is visible
    print("Checking for Citi Bot greeting message...")
    greeting_selectors = [
        "text=I'm Citi® Bot",
        "text=I'm Citi Bot", 
        "text=Citi® Bot",
        "text=here to help",
        "text=help with your account",
        "[class*='bot-message']",
        "[class*='assistant']",
    ]
    
    greeting_found = False
    for selector in greeting_selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                print(f"Bot greeting found: {selector}")
                greeting_found = True
                break
        except Exception:
            continue
    
    if not greeting_found:
        print("Bot greeting not explicitly found, but proceeding anyway...")
    
    # Take final screenshot
    try:
        page.screenshot(path="/tmp/citi_step5_bot_ready.png")
        print("Step 5 final screenshot saved - Bot ready!")
    except Exception:
        pass
    
    
    # Inject custom CSS to fix layout issues requested by user
    print("Injecting custom CSS for chat widget layout...")
    inject_custom_styles(page)
    
    # ALSO scroll the chat widget to show the input field
    print("Scrolling chat widget to show input field...")
    try:
        page.evaluate("""
            () => {
                // Find and scroll all chat-related containers to bottom
                const containers = document.querySelectorAll(
                    '[class*="chat"], [class*="Chat"], [class*="bot"], [class*="Bot"], ' +
                    '[class*="message"], [class*="conversation"]'
                );
                containers.forEach(container => {
                    if (container.scrollHeight > container.clientHeight) {
                        container.scrollTop = container.scrollHeight;
                    }
                });
                
                // Find the input field and scroll it into view
                const inputSelectors = [
                    'input[placeholder*="Write a message" i]',
                    'input[placeholder*="message" i]',
                    'textarea[placeholder*="message" i]'
                ];
                
                for (const selector of inputSelectors) {
                    const input = document.querySelector(selector);
                    if (input) {
                        input.scrollIntoView({ behavior: 'instant', block: 'center' });
                        input.focus();
                        console.log('Chat input scrolled into view:', selector);
                        return true;
                    }
                }
                return false;
            }
        """)
        print("Chat widget scrolled to show input")
    except Exception as e:
        print(f"Scroll failed: {e}")
    
    print("\n" + "=" * 60)
    print("CHAT WIDGET SETUP COMPLETE - READY TO SEND MESSAGES")
    print("=" * 60)
    
    # Brief final wait for stability
    page.wait_for_timeout(1000)

def inject_custom_styles(page: Page):
    """
    Inject CSS to make the chat input field FIXED at the bottom of the
    browser viewport, ensuring it's ALWAYS visible like in the screenshot.
    """
    try:
        # CSS to make chat input FIXED at bottom of viewport
        page.add_style_tag(content="""
            /* ============================================
               CHAT INPUT - FIXED AT BOTTOM OF VIEWPORT
               Makes "Write a message..." always visible at
               the bottom of the browser window
               ============================================ */
            
            /* Find and fix the input container at the bottom */
            /* Target parent containers that hold the input */
            form:has(input[placeholder*='Write a message' i]),
            form:has(input[placeholder*='message' i]),
            [class*='chat'] form:has(input),
            [class*='compose'],
            [class*='input-area']:has(input),
            [class*='chat'] [class*='footer']:has(input),
            div:has(> input[placeholder*='Write a message' i]) {
                position: fixed !important;
                bottom: 0 !important;
                left: 0 !important;
                right: 0 !important;
                width: 100% !important;
                z-index: 999999 !important;
                background: white !important;
                padding: 10px 15px !important;
                box-shadow: 0 -2px 10px rgba(0,0,0,0.1) !important;
                display: flex !important;
                align-items: center !important;
                gap: 10px !important;
                box-sizing: border-box !important;
            }
            
            /* The actual input field - make it prominent */
            input[placeholder*='Write a message' i],
            input[placeholder*='message' i],
            textarea[placeholder*='Write a message' i],
            textarea[placeholder*='message' i] {
                visibility: visible !important;
                opacity: 1 !important;
                display: block !important;
                flex: 1 !important;
                min-height: 40px !important;
                height: 40px !important;
                padding: 10px 15px !important;
                border: 1px solid #ccc !important;
                border-radius: 20px !important;
                font-size: 14px !important;
                z-index: 999999 !important;
                pointer-events: auto !important;
                background: #f5f5f5 !important;
            }
            
            /* Send button styling */
            [class*='chat'] button:has(svg),
            [class*='send'],
            button[type='submit'],
            button[aria-label*='send' i] {
                visibility: visible !important;
                opacity: 1 !important;
                z-index: 999999 !important;
                pointer-events: auto !important;
                min-width: 40px !important;
                min-height: 40px !important;
                border-radius: 50% !important;
                background: #0066b2 !important;
                cursor: pointer !important;
            }
            
            /* Ensure chat messages area has bottom padding for fixed input */
            [class*='chat'] [class*='message'],
            [class*='chat'] [class*='content'],
            [class*='chat'] [class*='conversation'],
            [class*='messaging'] {
                padding-bottom: 80px !important;
            }
            
            /* Make sure the chat container is visible and scrollable */
            [class*='chat-widget'],
            [class*='chat-window'],
            [class*='chat-panel'],
            [class*='messaging-container'] {
                min-height: 100vh !important;
                max-height: 100vh !important;
                overflow-y: auto !important;
            }
        """)
        print("CSS applied - chat input FIXED at bottom of viewport")
    except Exception as e:
        print(f"Failed to inject CSS: {e}")


def ensure_chat_input_visible(page: Page) -> bool:
    """
    Ensure the chat input field is visible and accessible.
    Uses broad selectors to find input within messaging/chat containers.
    Returns True if input was found and made visible.
    """
    try:
        # JavaScript to find and make chat input visible
        result = page.evaluate("""
            () => {
                // First, scroll all chat/messaging containers to bottom
                const chatContainers = document.querySelectorAll(
                    '[class*="chat"], [class*="Chat"], [class*="messaging"], [class*="Messaging"], ' +
                    '[class*="conversation"], [class*="bot"], [class*="Bot"], [class*="dialog"]'
                );
                
                chatContainers.forEach(container => {
                    if (container.scrollHeight > container.clientHeight) {
                        container.scrollTop = container.scrollHeight;
                    }
                });
                
                // BROAD search for chat input - try many patterns
                const inputSelectors = [
                    // Standard placeholder patterns
                    'input[placeholder*="Write a message" i]',
                    'textarea[placeholder*="Write a message" i]',
                    'input[placeholder*="message" i]',
                    'textarea[placeholder*="message" i]',
                    'input[placeholder*="type" i]',
                    'textarea[placeholder*="type" i]',
                    
                    // Aria-label patterns
                    'input[aria-label*="message" i]',
                    'textarea[aria-label*="message" i]',
                    'input[aria-label*="chat" i]',
                    'textarea[aria-label*="chat" i]',
                    '[aria-label*="compose" i]',
                    
                    // Contenteditable elements (some chats use these)
                    '[contenteditable="true"]',
                    '[role="textbox"]',
                    
                    // Class-based patterns for chat inputs
                    '[class*="chat-input"]',
                    '[class*="message-input"]',
                    '[class*="composer"] input',
                    '[class*="composer"] textarea',
                    '[class*="input-area"] input',
                    '[class*="input-area"] textarea',
                ];
                
                let input = null;
                for (const selector of inputSelectors) {
                    try {
                        input = document.querySelector(selector);
                        if (input && input.offsetParent !== null) break;
                        input = null; // Reset if not visible
                    } catch(e) {}
                }
                
                // Fallback: Search within messaging/chat containers for any input/textarea
                if (!input) {
                    const containers = document.querySelectorAll(
                        '[class*="messaging"], [class*="chat"], [class*="Chat"], [class*="citi"][class*="bot"]'
                    );
                    for (const container of containers) {
                        const inputs = container.querySelectorAll('input, textarea, [contenteditable="true"]');
                        for (const inp of inputs) {
                            // Skip hidden inputs or inputs with certain types
                            if (inp.type === 'hidden' || inp.type === 'checkbox' || inp.type === 'radio') continue;
                            if (inp.offsetParent !== null) {
                                input = inp;
                                break;
                            }
                        }
                        if (input) break;
                    }
                }
                
                if (input) {
                    // Scroll input into view
                    input.scrollIntoView({ behavior: 'instant', block: 'center' });
                    
                    // Ensure it's visible with inline styles
                    input.style.visibility = 'visible';
                    input.style.opacity = '1';
                    input.style.display = input.tagName === 'TEXTAREA' ? 'block' : 'inline-block';
                    
                    // Focus the input
                    input.focus();
                    
                    return {
                        found: true,
                        placeholder: input.placeholder || input.getAttribute('aria-label') || '',
                        tagName: input.tagName,
                        className: input.className?.substring(0, 50) || '',
                        visible: input.offsetParent !== null
                    };
                }
                
                // Debug: Return info about what we found
                const allInputs = document.querySelectorAll('input, textarea');
                const visibleInputs = Array.from(allInputs).filter(i => i.offsetParent !== null);
                return { 
                    found: false, 
                    totalInputs: allInputs.length,
                    visibleInputs: visibleInputs.length,
                    hint: 'Search for input within messaging container failed'
                };
            }
        """)
        
        if result and result.get('found'):
            print(f"Chat input found: {result.get('tagName')} placeholder='{result.get('placeholder', '')[:30]}' class='{result.get('className', '')[:30]}'")
            return True
        else:
            print(f"Chat input not found: {result}")
            return False
            
    except Exception as e:
        print(f"Error ensuring chat input visibility: {e}")
        return False

    
def process_utterance_with_llm(
    page: Page,
    utterance: str,
    test_run_id: int,
    session: Session
) -> Optional[dict]:
    """
    Send an utterance, capture response, and evaluate with LLM.
    Returns latency and quality score.
    """
    try:
        # CRITICAL: Ensure chat input is visible before attempting to interact
        ensure_chat_input_visible(page)
        page.wait_for_timeout(300)
        
        # Find the chat input
        input_selectors = [
            "input[placeholder*='message']",
            "textarea[placeholder*='message']",
            "input[placeholder*='type']",
            "[class*='input']",
            "[class*='chat-input']",
            "input[type='text']"
        ]
        
        input_field = None
        for selector in input_selectors:
            try:
                field = page.query_selector(selector)
                if field and field.is_visible():
                    input_field = field
                    break
            except Exception:
                continue
        
        if not input_field:
            print(f"Could not find input field for utterance: {utterance[:30]}...")
            return None
        
        # Record start time
        start_time = time.time()
        
        # Type the utterance - use force click and direct fill to avoid CDK wrapper issues
        try:
            # Try direct fill first (bypasses click interception)
            input_field.fill(utterance)
            print(f"Filled chat input using direct fill")
        except Exception as e1:
            try:
                # Force click then fill
                input_field.click(force=True)
                page.wait_for_timeout(200)
                input_field.fill(utterance)
                print(f"Filled chat input using force click + fill")
            except Exception as e2:
                # JavaScript fallback
                try:
                    input_field.evaluate(
                        "(el, val) => { el.focus(); el.value = val; el.dispatchEvent(new Event('input', { bubbles: true })); }",
                        utterance
                    )
                    print(f"Filled chat input using JavaScript")
                except Exception as e3:
                    print(f"All fill methods failed: {e3}")
                    return None
        
        # Wait a moment for the input to register
        page.wait_for_timeout(500)
        
        # Submit - try multiple approaches for Citi Bot's send button (circular arrow icon)
        send_selectors = [
            # Citi Bot specific selectors for the arrow/send button
            "[class*='send-button']",
            "[class*='submit-button']",
            "button[aria-label*='send' i]",
            "button[aria-label*='submit' i]",
            "[class*='chat'] button[type='button']",  # Often button type, not submit
            "[class*='input'] ~ button",
            "button svg circle",  # Arrow button has SVG
            "button:has(svg)",
            "[role='button'][class*='send']",
            "button[type='submit']",
            "[class*='send']",
            "button:has-text('Send')",
        ]
        
        sent = False
        for selector in send_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    try:
                        btn.click(force=True)
                        sent = True
                        print(f"Clicked send button: {selector}")
                        break
                    except Exception:
                        try:
                            btn.evaluate("el => el.click()")
                            sent = True
                            print(f"Clicked send button via JS: {selector}")
                            break
                        except Exception:
                            continue
            except Exception:
                continue
        
        # If no button worked, try keyboard Enter - this is the most reliable
        if not sent:
            page.keyboard.press("Enter")
            print("Submitted via Enter key")
            sent = True
        
        # Wait for bot response - give more time for Citi Bot
        page.wait_for_timeout(3000)
        
        # Try to capture the bot response with Citi Bot specific selectors
        response_selectors = [
            # Citi Bot specific message selectors
            "[class*='message-content']",
            "[class*='chat-message']",
            "[class*='bot-message']",
            "[class*='assistant-message']",
            "[class*='bubble']",
            "[class*='response']",
            "[class*='msg-text']",
            "[class*='message-text']",
        ]
        
        bot_response = ""
        for attempt in range(15):  # Try for ~7.5 seconds
            # First, try to get the last message that's NOT the user's message
            try:
                # Look for all message elements
                all_messages = page.query_selector_all("[class*='message']")
                if all_messages and len(all_messages) > 0:
                    # Get the last message content
                    for msg in reversed(all_messages):
                        text = (msg.text_content() or "").strip()
                        # Skip if it's the user's utterance, empty, or just a timestamp
                        if text and text != utterance and len(text) > 10 and not is_invalid_response(text):
                            bot_response = text
                            break
            except Exception:
                pass
            
            if bot_response:
                break
            
            # Fallback: try specific selectors
            for selector in response_selectors:
                try:
                    elements = page.query_selector_all(selector)
                    if elements:
                        latest = elements[-1]
                        text = (latest.text_content() or "").strip()
                        if text and text != utterance and len(text) > 10 and not is_invalid_response(text):
                            bot_response = text
                            break
                except Exception:
                    continue
            
            if bot_response:
                break
            
            page.wait_for_timeout(500)
        
        # Record end time
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        # Get category and expected intent
        category = get_category_for_utterance(utterance)
        expected_intent = get_expected_intent(category)
        
        # Evaluate with LLM
        evaluation = evaluate_response(utterance, bot_response, expected_intent)
        
        # Determine status
        if not bot_response:
            status = "error"
        elif detect_escalation(bot_response):
            status = "escalated"
        else:
            status = "pass"
        
        # Save conversation log
        log = ConversationLog(
            test_run_id=test_run_id,
            utterance=utterance,
            bot_response=bot_response[:2000] if bot_response else "",
            latency_ms=latency_ms,
            status=status,
            category=category,
            timestamp=get_local_now(),
            # LLM evaluation fields
            relevance_score=evaluation.relevance_score if evaluation else None,
            helpfulness_score=evaluation.helpfulness_score if evaluation else None,
            clarity_score=evaluation.clarity_score if evaluation else None,
            accuracy_score=evaluation.accuracy_score if evaluation else None,
            overall_score=evaluation.overall_score if evaluation else None,
            sentiment=evaluation.sentiment if evaluation else None,
            llm_feedback=evaluation.improvement_suggestion if evaluation else None,
        )
        session.add(log)
        session.commit()
        
        print(f"Processed: '{utterance[:40]}...' -> latency={latency_ms}ms, score={evaluation.overall_score if evaluation else 'N/A'}")
        
        return {
            "latency": latency_ms,
            "quality_score": evaluation.overall_score if evaluation else None
        }
        
    except Exception as e:
        print(f"Error processing utterance: {e}")
        # Save error log
        log = ConversationLog(
            test_run_id=test_run_id,
            utterance=utterance,
            bot_response=f"Error: {str(e)}",
            latency_ms=0,
            status="error",
            category=get_category_for_utterance(utterance),
            timestamp=get_local_now()
        )
        session.add(log)
        session.commit()
        return None


def update_test_run_metrics(
    session: Session,
    test_run_id: int,
    latencies: List[int],
    quality_scores: List[float]
):
    """Calculate and save metrics for the test run."""
    test_run = session.get(TestRun, test_run_id)
    if not test_run:
        return
    
    # Get all logs for this test run
    logs = session.query(ConversationLog).filter(
        ConversationLog.test_run_id == test_run_id
    ).all()
    
    total = len(logs)
    passed = sum(1 for log in logs if log.status == "pass")
    escalated = sum(1 for log in logs if log.status == "escalated")
    
    # Calculate basic metrics
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    self_service_rate = ((total - escalated) / total * 100) if total > 0 else 0
    
    # Calculate quality metrics
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    
    relevance_scores = [log.relevance_score for log in logs if log.relevance_score]
    helpfulness_scores = [log.helpfulness_score for log in logs if log.helpfulness_score]
    
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0
    avg_helpfulness = sum(helpfulness_scores) / len(helpfulness_scores) if helpfulness_scores else 0
    
    # Update test run
    test_run.status = "completed"
    test_run.completed_at = get_local_now()
    test_run.total_utterances = total
    test_run.avg_latency_ms = round(avg_latency, 2)
    test_run.self_service_rate = round(self_service_rate, 2)
    test_run.avg_quality_score = round(avg_quality, 2)
    test_run.avg_relevance_score = round(avg_relevance, 2)
    test_run.avg_helpfulness_score = round(avg_helpfulness, 2)
    
    session.add(test_run)
    session.commit()
    
    print(f"Test completed: {total} utterances, avg latency={avg_latency:.0f}ms, quality={avg_quality:.1f}/10")


# Keep the old function for backwards compatibility
def run_chatbot_test(
    test_run_id: int,
    target_url: str,
    utterances: List[str],
    credentials: Optional[Credentials] = None,
    chatbot_config: Optional[ChatbotConfig] = None
):
    """Wrapper that calls the Citi-specific test."""
    run_citi_chatbot_test(test_run_id, target_url, utterances, credentials, chatbot_config)


# ============ ADAPTIVE TESTING FUNCTIONS ============

def extract_menu_options(page: Page, wait_for_options: bool = True) -> List[str]:
    """
    Extract clickable menu options from WITHIN the chat widget.
    
    Enhanced version that:
    1. Uses JavaScript for reliable DOM detection
    2. Detects various clickable element types (buttons, links, chips)
    3. Waits for options to appear after bot questions
    4. Has smarter filtering logic
    
    Args:
        page: Playwright page object
        wait_for_options: If True, wait extra time for menu options to appear
        
    Returns:
        List of clickable option text strings
    """
    menu_options = []
    
    # If waiting for options, give time for them to render after bot response
    if wait_for_options:
        page.wait_for_timeout(1500)
    
    # Use JavaScript for more reliable detection - this handles dynamic content better
    try:
        options_data = page.evaluate("""
            () => {
                const options = [];
                const seen = new Set();
                
                // Skip patterns - navigation and action buttons we don't want to click
                const skipPatterns = [
                    /^send$/i, /^submit$/i, /^close$/i, /^x$/i, /^minimize$/i,
                    /^sign off$/i, /^sign on$/i, /^help$/i, /^menu$/i,
                    /^see more$/i, /^learn more$/i, /^view account$/i,
                    /^go to/i, /^navigate/i, /^open$/i,
                    /thumbs (up|down)/i, /was this helpful/i,
                    /^read$/i, /^today/i
                ];
                
                // Account-related patterns we definitely want to capture
                const accountPatterns = [
                    /card/i, /citi/i, /checking/i, /savings/i,
                    /strata/i, /double cash/i, /custom cash/i,
                    /\\.{3}\\d{4}$/,  // Matches "...1234" pattern
                    /account.*\\d{4}/i
                ];
                
                // Action patterns we want to capture for multi-turn flows
                const actionPatterns = [
                    /balance/i, /payment/i, /dispute/i, /reward/i,
                    /replace/i, /lock/i, /unlock/i, /transfer/i,
                    /isn't listed/i, /not listed/i
                ];
                
                // Confirmation patterns - Yes/No buttons for confirmations
                const confirmationPatterns = [
                    /^yes$/i, /^no$/i, /^confirm$/i, /^cancel$/i,
                    /^ok$/i, /^okay$/i, /^continue$/i, /^done$/i,
                    /^agree$/i, /^decline$/i, /^accept$/i, /^reject$/i,
                    /^that's right$/i, /^that's correct$/i,
                    /^that's not right$/i, /^not correct$/i
                ];
                
                // Find the chat container first
                const chatContainerSelectors = [
                    '[class*="citi"][class*="bot"]',
                    '[class*="chat-widget"]', 
                    '[class*="chat-container"]',
                    '[class*="chatbot"]',
                    '[class*="messaging"]',
                    '[id*="chat"]',
                    '[class*="dialog"][class*="bot"]'
                ];
                
                let chatContainer = null;
                for (const selector of chatContainerSelectors) {
                    const el = document.querySelector(selector);
                    if (el && el.offsetParent !== null) {
                        chatContainer = el;
                        break;
                    }
                }
                
                // If no chat container, search entire page but be more careful
                const searchRoot = chatContainer || document.body;
                
                // Selectors for clickable elements that could be menu options
                const clickableSelectors = [
                    // Buttons and button-like elements
                    'button:not([disabled])',
                    '[role="button"]',
                    '[role="option"]',
                    '[role="listitem"]',
                    
                    // Links that look like options
                    'a[href="#"]',
                    'a:not([href^="http"]):not([href^="/"])',
                    
                    // Chip/pill style elements
                    '[class*="chip"]',
                    '[class*="pill"]',
                    '[class*="tag"]',
                    
                    // Quick reply / suggestion elements
                    '[class*="quick-reply"]',
                    '[class*="quickreply"]',
                    '[class*="suggestion"]',
                    '[class*="option"]',
                    '[class*="choice"]',
                    
                    // Citi-specific patterns
                    '[class*="account-option"]',
                    '[class*="account-item"]',
                    '[class*="selection"]',
                    '[class*="selectable"]',
                    
                    // Clickable divs/spans often used for chat options
                    '[onclick]',
                    '[class*="clickable"]',
                    '[tabindex="0"]'
                ];
                
                for (const selector of clickableSelectors) {
                    try {
                        const elements = searchRoot.querySelectorAll(selector);
                        for (const el of elements) {
                            // Skip invisible elements
                            if (el.offsetParent === null && el.style.position !== 'fixed') continue;
                            
                            // Get text content
                            let text = (el.textContent || '').trim();
                            
                            // Clean up text - remove extra whitespace
                            text = text.replace(/\\s+/g, ' ').trim();
                            
                            // Skip if already seen, too short, or too long
                            if (seen.has(text.toLowerCase())) continue;
                            
                            // Check if it matches confirmation patterns FIRST (allows short text like "Yes", "No")
                            const isConfirmation = confirmationPatterns.some(p => p.test(text));
                            
                            // Skip based on length - but allow short confirmations like "Yes", "No", "Ok"
                            if (!isConfirmation && (text.length < 3 || text.length > 80)) continue;
                            if (isConfirmation && text.length > 20) continue;  // Confirmations shouldn't be too long
                            
                            // Skip if matches skip patterns
                            if (skipPatterns.some(p => p.test(text))) continue;
                            
                            // Skip transaction entries (have $ with dates)
                            if (text.includes('$') && (/posted/i.test(text) || /\\d{1,2}[,\\/]\\s*\\d{4}/.test(text))) continue;
                            
                            // Skip timestamp-only text
                            if (/^\\d{1,2}:\\d{2}\\s*(am|pm)?$/i.test(text)) continue;
                            
                            // Check if it matches account or action patterns - these we definitely want
                            const isAccountOption = accountPatterns.some(p => p.test(text));
                            const isActionOption = actionPatterns.some(p => p.test(text));
                            
                            // For elements in chat container, be more permissive
                            // For elements outside, only accept if they match known patterns
                            if (chatContainer || isAccountOption || isActionOption || isConfirmation) {
                                seen.add(text.toLowerCase());
                                options.push({
                                    text: text,
                                    isAccount: isAccountOption,
                                    isAction: isActionOption,
                                    isConfirmation: isConfirmation,
                                    tag: el.tagName,
                                    classes: el.className.substring(0, 50)
                                });
                            }
                        }
                    } catch (e) {
                        // Selector might not be valid, continue
                    }
                }
                
                return options;
            }
        """)
        
        if options_data:
            print(f"[MenuOptions] JavaScript found {len(options_data)} potential options:")
            for opt in options_data[:8]:
                flags = []
                if opt.get('isAccount'): flags.append('account')
                if opt.get('isAction'): flags.append('action')
                if opt.get('isConfirmation'): flags.append('confirm')
                flags_str = ','.join(flags) if flags else 'other'
                print(f"  - '{opt['text'][:40]}' ({flags_str}, tag={opt['tag']})")
            
            # Prioritize: account options → action options → confirmations → others
            account_opts = [o['text'] for o in options_data if o.get('isAccount')]
            action_opts = [o['text'] for o in options_data if o.get('isAction') and o['text'] not in account_opts]
            confirm_opts = [o['text'] for o in options_data if o.get('isConfirmation') and o['text'] not in account_opts and o['text'] not in action_opts]
            other_opts = [o['text'] for o in options_data if not o.get('isAccount') and not o.get('isAction') and not o.get('isConfirmation')]
            
            # Combine with priority ordering
            menu_options = account_opts + action_opts + confirm_opts + other_opts[:5]  # Limit others
            
    except Exception as e:
        print(f"[MenuOptions] JavaScript extraction failed: {e}")
    
    # Fallback: Use Playwright locators if JavaScript found nothing
    if not menu_options:
        print("[MenuOptions] Fallback to Playwright locators...")
        
        fallback_selectors = [
            "button:has-text('Card')",
            "button:has-text('Citi')",
            "button:has-text('Checking')",
            "button:has-text('Savings')",
            "[role='button']:has-text('Card')",
            "a:has-text('Card')",
            "[class*='option']:has-text('Card')",
        ]
        
        for selector in fallback_selectors:
            try:
                elements = page.locator(selector)
                count = elements.count()
                for i in range(min(count, 5)):
                    try:
                        el = elements.nth(i)
                        if el.is_visible(timeout=300):
                            text = (el.text_content() or "").strip()
                            if text and text not in menu_options and len(text) < 80:
                                menu_options.append(text)
                                print(f"  Fallback found: '{text[:40]}' via {selector}")
                    except Exception:
                        continue
            except Exception:
                continue
    
    # Deduplicate while preserving order
    seen = set()
    unique_options = []
    for opt in menu_options:
        opt_lower = opt.lower()
        if opt_lower not in seen:
            seen.add(opt_lower)
            unique_options.append(opt)
    
    print(f"[MenuOptions] Final: {len(unique_options)} options - {unique_options[:5]}")
    return unique_options


def click_menu_option(page: Page, option_text: str) -> bool:
    """
    Click a menu option by its text.
    
    Enhanced version with multiple strategies:
    1. Exact text match via Playwright
    2. Partial/contains text match
    3. JavaScript-based click with fuzzy matching
    4. Debug screenshot on failure
    
    ENHANCED: Added post-click verification to ensure DOM changed.
    
    Args:
        page: Playwright page object
        option_text: Text of the option to click
        
    Returns:
        True if clicked successfully, False otherwise
    """
    print(f"[ClickMenu] Attempting to click: '{option_text}'")
    
    # Capture menu options before click to verify change
    def get_current_options():
        try:
            return extract_menu_options(page, wait_for_options=False)
        except:
            return []
    
    options_before = get_current_options()
    
    def verify_click_success():
        """Check if DOM changed after click (new response or different options)."""
        page.wait_for_timeout(1000)
        options_after = get_current_options()
        
        # Success if: options changed, or we got a new bot narrative
        if set(options_after) != set(options_before):
            return True
        
        # Also check if bot response changed
        try:
            narrative = extract_bot_narrative_text(page)
            if narrative and len(narrative) > 15:
                # There's some narrative response, likely successful
                return True
        except:
            pass
        
        return False
    
    # Strategy 1: Direct Playwright text match (various element types)
    direct_selectors = [
        f"button:has-text('{option_text}')",
        f"a:has-text('{option_text}')",
        f"[role='button']:has-text('{option_text}')",
        f"[role='option']:has-text('{option_text}')",
        f"[role='listitem']:has-text('{option_text}')",
        f"[class*='option']:has-text('{option_text}')",
        f"[class*='chip']:has-text('{option_text}')",
        f"[tabindex='0']:has-text('{option_text}')",
    ]
    
    for selector in direct_selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=1000):
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(200)
                el.click(force=True)
                print(f"[ClickMenu] SUCCESS via Playwright: '{option_text}' using {selector}")
                page.wait_for_timeout(1500)  # Wait for response after click
                
                # Verify the click worked
                if verify_click_success():
                    print(f"[ClickMenu] Verified: DOM changed after click")
                    return True
                else:
                    print(f"[ClickMenu] Warning: Click may not have registered, trying alternative...")
                    # Continue to try other methods
        except Exception as e:
            continue
    
    # Strategy 2: Partial text match (useful for truncated text like "Citi Double Cash...")
    # Extract a unique substring to match
    partial_text = option_text[:20] if len(option_text) > 20 else option_text
    partial_selectors = [
        f"button:has-text('{partial_text}')",
        f"a:has-text('{partial_text}')",
        f"[role='button']:has-text('{partial_text}')",
    ]
    
    for selector in partial_selectors:
        try:
            elements = page.locator(selector)
            count = elements.count()
            for i in range(min(count, 5)):
                el = elements.nth(i)
                if el.is_visible(timeout=500):
                    text = (el.text_content() or "").strip()
                    # Check if this is the right match
                    if option_text.lower() in text.lower() or text.lower() in option_text.lower():
                        el.scroll_into_view_if_needed()
                        page.wait_for_timeout(200)
                        el.click(force=True)
                        print(f"[ClickMenu] SUCCESS via partial match: '{text[:40]}' using {selector}")
                        page.wait_for_timeout(1500)
                        
                        if verify_click_success():
                            return True
        except Exception:
            continue
    
    # Strategy 3: JavaScript-based click with case-insensitive matching
    # This is more flexible and handles dynamic elements better
    try:
        js_result = page.evaluate("""
            (targetText) => {
                const searchText = targetText.toLowerCase();
                
                // Selectors to search (in priority order)
                const selectors = [
                    'button', 'a', '[role="button"]', '[role="option"]',
                    '[class*="chip"]', '[class*="option"]', '[class*="selection"]',
                    '[tabindex="0"]', '[onclick]'
                ];
                
                for (const selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        // Skip hidden elements
                        if (el.offsetParent === null && el.style.position !== 'fixed') continue;
                        
                        const elText = (el.textContent || '').trim().toLowerCase();
                        
                        // Check for exact match or contains match
                        if (elText === searchText || 
                            elText.includes(searchText) || 
                            searchText.includes(elText)) {
                            
                            // Scroll into view first
                            el.scrollIntoView({ behavior: 'instant', block: 'center' });
                            
                            // Try to dispatch a proper click event
                            const event = new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            });
                            el.dispatchEvent(event);
                            
                            return {
                                success: true,
                                clickedText: el.textContent.trim().substring(0, 50),
                                selector: selector
                            };
                        }
                    }
                }
                
                return { success: false };
            }
        """, option_text)
        
        if js_result and js_result.get('success'):
            print(f"[ClickMenu] SUCCESS via JavaScript: '{js_result.get('clickedText')}' using {js_result.get('selector')}")
            page.wait_for_timeout(1500)
            
            if verify_click_success():
                return True
            
    except Exception as e:
        print(f"[ClickMenu] JavaScript click failed: {e}")
    
    # Strategy 4: Try clicking by exact text with get_by_text
    try:
        el = page.get_by_text(option_text, exact=False).first
        if el.is_visible(timeout=1000):
            el.click(force=True)
            print(f"[ClickMenu] SUCCESS via get_by_text: '{option_text}'")
            page.wait_for_timeout(1500)
            
            if verify_click_success():
                return True
    except Exception:
        pass
    
    # Strategy 5: Double-click as last resort (some chat widgets need this)
    try:
        el = page.get_by_text(option_text, exact=False).first
        if el.is_visible(timeout=500):
            el.dblclick(force=True)
            print(f"[ClickMenu] Trying double-click: '{option_text}'")
            page.wait_for_timeout(1500)
            
            if verify_click_success():
                return True
    except Exception:
        pass
    
    # Failed - capture debug screenshot
    print(f"[ClickMenu] FAILED to click: '{option_text}'")
    try:
        screenshot_path = f"/tmp/click_menu_failed_{option_text[:20].replace(' ', '_')}.png"
        page.screenshot(path=screenshot_path)
        print(f"[ClickMenu] Debug screenshot saved: {screenshot_path}")
    except Exception:
        pass
    
    return False


def wait_for_menu_options(page: Page, timeout_ms: int = 5000) -> List[str]:
    """
    Wait for menu options to appear after a bot response.
    
    This is useful when the bot asks a clarifying question and we need
    to wait for the clickable options to render.
    
    Args:
        page: Playwright page object
        timeout_ms: Maximum time to wait for options
        
    Returns:
        List of menu option texts found
    """
    print(f"[WaitForMenu] Waiting up to {timeout_ms}ms for menu options...")
    
    elapsed = 0
    check_interval = 500
    last_count = 0
    stable_checks = 0
    
    while elapsed < timeout_ms:
        # Extract current menu options (without waiting)
        options = extract_menu_options(page, wait_for_options=False)
        
        if options:
            # Check if options are stable (same count for 2 checks)
            if len(options) == last_count:
                stable_checks += 1
                if stable_checks >= 2:
                    print(f"[WaitForMenu] Found {len(options)} stable options after {elapsed}ms")
                    return options
            else:
                stable_checks = 0
                last_count = len(options)
        
        page.wait_for_timeout(check_interval)
        elapsed += check_interval
    
    # Return whatever we have after timeout
    final_options = extract_menu_options(page, wait_for_options=False)
    print(f"[WaitForMenu] Timeout reached, returning {len(final_options)} options")
    return final_options


def detect_clarifying_question(bot_response: str) -> bool:
    """
    Detect if the bot is asking a clarifying question that expects user selection.
    
    Args:
        bot_response: The bot's response text
        
    Returns:
        True if bot is asking for clarification/selection
    """
    if not bot_response:
        return False
    
    response_lower = bot_response.lower()
    
    # Patterns that indicate bot is asking for user selection or confirmation
    clarifying_patterns = [
        # Account selection patterns
        "which account",
        "which card",
        "select an account",
        "choose an account",
        "would you like to check",
        "would you like to",
        "please select",
        "please choose",
        "here are",
        "here's a list",
        "following options",
        "you can select",
        "pick one",
        # Confirmation question patterns (Yes/No expected)
        "is this correct",
        "is that correct",
        "is this right",
        "is that right",
        "does this look right",
        "confirm your",
        "would you like to continue",
        "do you want to",
        "should i proceed",
        "is this the account",
        "is this the card",
    ]
    
    return any(pattern in response_lower for pattern in clarifying_patterns)


def detect_yes_no_confirmation(bot_response: str) -> bool:
    """
    Detect if the bot is asking a Yes/No confirmation question.
    
    These patterns indicate the bot expects "Yes" or "No" response,
    NOT another menu option click.
    
    Args:
        bot_response: The bot's response text
        
    Returns:
        True if bot is asking a Yes/No confirmation question
    """
    if not bot_response:
        return False
    
    response_lower = bot_response.lower()
    
    # Patterns that specifically indicate Yes/No confirmation expected
    confirmation_patterns = [
        ", right?",
        "is that for",
        "is this for",
        "is that correct",
        "is this correct",
        "correct?",
        "want to make sure",
        "just to confirm",
        "would you like to continue",
        "do you want to proceed",
        "shall i continue",
        "is this the one",
        "are you sure",
    ]
    
    return any(pattern in response_lower for pattern in confirmation_patterns)


def send_message_and_get_response(page: Page, message: str) -> str:
    """
    Send a message in the chat and capture bot response.
    Returns the bot's response text.
    """
    try:
        # CRITICAL: Ensure chat input is visible before attempting to type
        ensure_chat_input_visible(page)
        page.wait_for_timeout(300)
        
        # First, scroll the chat widget to make input visible at bottom
        # This is important because chat input is at the bottom of the widget
        try:
            page.evaluate("""
                () => {
                    // Find chat container and scroll to bottom
                    const chatContainers = document.querySelectorAll('[class*="chat"], [class*="message-container"], [class*="conversation"]');
                    chatContainers.forEach(container => {
                        container.scrollTop = container.scrollHeight;
                    });
                    // Also scroll any scrollable parent
                    const inputs = document.querySelectorAll('input[placeholder*="message" i], textarea[placeholder*="message" i]');
                    inputs.forEach(input => {
                        input.scrollIntoView({ behavior: 'instant', block: 'center' });
                    });
                }
            """)
        except Exception:
            pass
        
        page.wait_for_timeout(500)
        
        # Find chat input - CITI BOT uses a contenteditable DIV with class 'chat-input-box'
        input_selectors = [
            # CITI BOT SPECIFIC - contenteditable div
            ".chat-input-box",
            "[class*='chat-input-box']",
            "[contenteditable='true'][class*='chat']",
            "[contenteditable='true']",
            "[role='textbox']",
            # Standard input/textarea selectors
            "input[placeholder*='Write a message' i]",
            "textarea[placeholder*='Write a message' i]",
            "input[placeholder*='message' i]",
            "textarea[placeholder*='message' i]",
            "input[placeholder*='type' i]",
            "input[placeholder*='Type' i]",
            "input[placeholder*='Write' i]",
            "textarea[placeholder*='Write' i]",
            "[class*='chat-input'] input",
            "[class*='chat-input'] textarea",
            "[class*='message-input'] input",
            "[class*='message-input'] textarea",
            "[class*='composer'] input",
            "[class*='composer'] textarea",
            "[class*='chat'] input[type='text']",
            "[class*='chat'] textarea",
            "[class*='bot'] input",
            "[class*='bot'] textarea",
        ]
        
        # First, try to scroll the widget to make input visible
        try:
            page.evaluate("""
                () => {
                    // Scroll all potential chat containers to bottom
                    const containers = document.querySelectorAll('[class*="chat"], [class*="message"], [class*="conversation"], [class*="bot"]');
                    containers.forEach(c => {
                        if (c.scrollHeight > c.clientHeight) {
                            c.scrollTop = c.scrollHeight;
                        }
                    });
                    
                    // Find input and scroll it into view
                    const input = document.querySelector('input[placeholder*="message" i], textarea[placeholder*="message" i], input[placeholder*="Write" i]');
                    if (input) {
                        input.scrollIntoView({ behavior: 'instant', block: 'center' });
                        input.focus();
                        return true;
                    }
                    return false;
                }
            """)
        except Exception:
            pass
        
        page.wait_for_timeout(500)
        
        input_field = None
        for selector in input_selectors:
            try:
                field = page.locator(selector).first
                if field.is_visible(timeout=500):
                    input_field = field
                    print(f"Found chat input: {selector}")
                    break
            except Exception:
                continue
        
        if not input_field:
            # Debug: List all inputs and textareas on the page
            try:
                all_inputs = page.evaluate("""
                    () => {
                        const inputs = document.querySelectorAll('input, textarea');
                        return Array.from(inputs).map(el => ({
                            tag: el.tagName,
                            type: el.type,
                            placeholder: el.placeholder,
                            visible: el.offsetParent !== null,
                            className: el.className.substring(0, 50)
                        }));
                    }
                """)
                print(f"DEBUG: Found {len(all_inputs)} input/textarea elements on page:")
                for inp in all_inputs[:10]:  # Show first 10
                    print(f"  - {inp}")
            except Exception as e:
                print(f"DEBUG: Error listing inputs: {e}")
            
            # Take a debug screenshot to see what's on screen
            try:
                page.screenshot(path="/tmp/debug_no_input_found.png")
                print("Debug screenshot saved to /tmp/debug_no_input_found.png")
            except Exception:
                pass
            
            # Try JavaScript to find and focus input - with broader search
            try:
                found = page.evaluate("""
                    () => {
                        // Try multiple approaches to find the input
                        let input = document.querySelector('input[placeholder*="message" i], textarea[placeholder*="message" i]');
                        if (!input) {
                            input = document.querySelector('input[placeholder*="Write" i], textarea[placeholder*="Write" i]');
                        }
                        if (!input) {
                            // Look for any visible input/textarea in chat-like containers
                            const containers = document.querySelectorAll('[class*="chat"], [class*="bot"], [class*="messaging"]');
                            for (const container of containers) {
                                const inp = container.querySelector('input, textarea');
                                if (inp && inp.offsetParent !== null) {
                                    input = inp;
                                    break;
                                }
                            }
                        }
                        if (input) {
                            input.focus();
                            input.scrollIntoView({ behavior: 'instant', block: 'center' });
                            return true;
                        }
                        return false;
                    }
                """)
                if found:
                    page.wait_for_timeout(300)
                    # Try again after JS focus
                    for selector in input_selectors[:4]:
                        try:
                            field = page.locator(selector).first
                            if field.is_visible(timeout=500):
                                input_field = field
                                print(f"Found chat input after JS focus: {selector}")
                                break
                        except Exception:
                            continue
            except Exception:
                pass
        
        if not input_field:
            print(f"Could not find input field for message: {message[:30]}...")
            return ""
        
        # Clear and type message - HANDLE CONTENTEDITABLE DIV (chat-input-box)
        try:
            # Click to focus first
            input_field.click(force=True)
            page.wait_for_timeout(200)
            
            # Check if it's a contenteditable div or regular input
            tag_name = input_field.evaluate("el => el.tagName")
            is_contenteditable = input_field.evaluate("el => el.contentEditable === 'true'")
            
            if tag_name.upper() == "DIV" or is_contenteditable:
                # For contenteditable div - use innerText and trigger input event
                print(f"Detected contenteditable element ({tag_name}), using innerText method")
                input_field.evaluate(
                    """(el, val) => {
                        el.focus();
                        el.innerText = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    message
                )
                print(f"Filled contenteditable with message: {message[:30]}...")
            else:
                # For regular input/textarea - use fill()
                input_field.fill(message)
                print(f"Filled input with message: {message[:30]}...")
        except Exception as e1:
            try:
                # JavaScript fallback - handles both input and contenteditable
                input_field.evaluate(
                    """(el, val) => {
                        el.focus();
                        if (el.contentEditable === 'true' || el.tagName === 'DIV') {
                            el.innerText = val;
                        } else {
                            el.value = val;
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    message
                )
                print(f"Filled message via JS fallback: {message[:30]}...")
            except Exception as e2:
                # Last resort: type character by character
                try:
                    input_field.click(force=True)
                    page.keyboard.type(message)
                    print(f"Typed message via keyboard: {message[:30]}...")
                except Exception as e3:
                    print(f"Failed to fill message: {e1}, {e2}, {e3}")
                    return ""
        
        # Wait for input to register
        page.wait_for_timeout(500)
        
        # Send message - try send button first, then Enter
        send_selectors = [
            "[class*='send-button']",
            "[class*='submit-button']",
            "button[aria-label*='send' i]",
            "button:has(svg)",
            "button[type='submit']",
            "button[type='button']:near(input[placeholder*='message' i])",
        ]
        
        sent = False
        for selector in send_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    btn.click(force=True)
                    sent = True
                    print(f"Clicked send button: {selector}")
                    break
            except Exception:
                continue
        
        if not sent:
            page.keyboard.press("Enter")
            print("Sent message via Enter key")
        
        # Wait for response - give more time for bot to fully respond with menus
        page.wait_for_timeout(5000)  # Increased from 3000 to allow bot to render menu options
        
        # ENHANCED: Try to capture clean narrative response first
        bot_response = ""
        
        # FIRST: Try extract_bot_narrative_text for clean response
        try:
            narrative = extract_bot_narrative_text(page)
            if narrative and len(narrative) > 15 and narrative.lower() != message.lower():
                if not is_invalid_response(narrative):
                    bot_response = narrative
                    print(f"[SendMessage] Got narrative response: {bot_response[:60]}...")
        except Exception as e:
            print(f"[SendMessage] Narrative extraction failed: {e}")
        
        # FALLBACK: Use selector-based approach with button filtering
        if not bot_response:
            response_selectors = [
                "[class*='message-content']",
                "[class*='chat-message']",
                "[class*='bot-message']",
                "[class*='assistant-message']",
                "[class*='bubble']",
                "[class*='response']",
                "[class*='msg-text']",
            ]
            
            for attempt in range(15):  # Try for ~7.5 seconds
                # Try to get messages
                try:
                    all_messages = page.query_selector_all("[class*='message']")
                    if all_messages and len(all_messages) > 0:
                        for msg in reversed(all_messages):
                            raw_text = (msg.text_content() or "").strip()
                            if raw_text and raw_text.lower() != message.lower() and len(raw_text) > 10:
                                # Filter out button text
                                filtered = filter_button_text_from_response(raw_text)
                                if filtered and len(filtered) > 10 and not is_invalid_response(filtered):
                                    bot_response = filtered
                                    break
                except Exception:
                    pass
                
                if bot_response:
                    break
                
                for selector in response_selectors:
                    try:
                        elements = page.query_selector_all(selector)
                        if elements:
                            latest = elements[-1]
                            raw_text = (latest.text_content() or "").strip()
                            if raw_text and raw_text.lower() != message.lower() and len(raw_text) > 10:
                                filtered = filter_button_text_from_response(raw_text)
                                if filtered and len(filtered) > 10 and not is_invalid_response(filtered):
                                    bot_response = filtered
                                    break
                    except Exception:
                        continue
                
                if bot_response:
                    break
                page.wait_for_timeout(500)
        
        print(f"Bot response: {bot_response[:50]}..." if bot_response else "No response captured")
        return bot_response
        
    except Exception as e:
        print(f"Error sending message: {e}")
        return ""


def run_adaptive_test(
    page: Page,
    utterance: str,
    test_run_id: int,
    session: Session,
    max_turns: int = 5
) -> dict:
    """
    Run adaptive test for a single utterance with LLM-driven flow.
    
    Enhanced features:
    - Dynamic turn limits based on progress
    - Partial success tracking
    - Context-aware follow-up prompts
    - Better timeout handling
    
    Args:
        page: Playwright page object
        utterance: Initial user question/utterance
        test_run_id: Test run ID for logging
        session: Database session
        max_turns: Maximum conversation turns before stopping
    
    Returns:
        Dict with test results
    """
    print(f"\n{'='*60}")
    print(f"ADAPTIVE TEST: {utterance[:50]}...")
    print(f"{'='*60}")
    
    start_time = time.time()
    current_message = utterance
    action_history = []
    menu_clicks = []
    turn = 0
    final_decision = None
    progress_made = False  # Track if we're making progress
    best_response = ""  # Track best response for partial success
    best_score = 0.0
    last_menu_choice = ""  # Track last choice for loop detection
    consecutive_same_choice = 0  # Count consecutive same selections
    
    # Get category for context-aware handling
    category = get_category_for_utterance(utterance)
    
    for turn in range(max_turns):
        print(f"\n[Turn {turn + 1}] Sending: {current_message[:40]}...")
        
        # Send message and get response with stabilization
        bot_response = send_message_and_get_response(page, current_message)
        
        # If no response, try wait_for_stable_response as fallback with longer timeout
        if not bot_response or is_invalid_response(bot_response):
            print(f"[Turn {turn + 1}] Waiting for stable response...")
            bot_response = wait_for_stable_response(page, timeout_ms=10000)  # Increased from 8000
        
        # 📸 CAPTURE SCREENSHOT AT EACH TURN for debugging
        screenshot_path = ""
        try:
            screenshot_suffix = f"turn{turn+1}"
            screenshot_path = capture_screenshot(page, test_run_id, utterance, "debug", screenshot_suffix)
        except Exception as e:
            print(f"[Turn {turn + 1}] Screenshot capture failed: {e}")
        
        # 🔍 VISION ANALYSIS: Use Gemini Vision to analyze what the bot is showing
        vision_analysis = None
        vision_menu_options = []
        if screenshot_path and os.path.exists(screenshot_path):
            try:
                vision_analysis = analyze_screenshot_with_vision(screenshot_path, utterance)
                if vision_analysis:
                    # Use vision-extracted bot message if DOM parsing missed it
                    if vision_analysis.bot_message and (not bot_response or len(vision_analysis.bot_message) > len(bot_response)):
                        print(f"[Turn {turn + 1}] 👁️ Vision found better bot message: {vision_analysis.bot_message[:60]}...")
                        bot_response = vision_analysis.bot_message
                    
                    # Capture vision-detected menu options
                    if vision_analysis.menu_options:
                        vision_menu_options = vision_analysis.menu_options
                        print(f"[Turn {turn + 1}] 👁️ Vision detected menu options: {vision_menu_options}")
            except Exception as e:
                print(f"[Turn {turn + 1}] Vision analysis failed: {e}")
        
        print(f"[Turn {turn + 1}] Bot: {bot_response[:100]}..." if bot_response else f"[Turn {turn + 1}] No response")
        
        # Track best response for partial success
        if bot_response:
            # Calculate local score for this response
            local_score = get_response_quality_score(bot_response, category)
            if local_score > best_score:
                best_score = local_score
                best_response = bot_response
                progress_made = True
        
        # ENHANCED: Detect if bot is asking a clarifying question
        # If so, we need to wait longer for menu options to appear
        is_clarifying = detect_clarifying_question(bot_response)
        if is_clarifying:
            print(f"[Turn {turn + 1}] Detected clarifying question - waiting for menu options...")
            # Wait longer for menu options when we know bot is asking for selection
            menu_options = wait_for_menu_options(page, timeout_ms=6000)
        else:
            # Standard menu extraction with wait
            menu_options = extract_menu_options(page, wait_for_options=True)
        
        # 👁️ MERGE VISION-DETECTED OPTIONS: Vision analysis often finds options DOM parsing misses
        if vision_menu_options:
            # Combine unique options, prioritizing vision-detected ones
            existing_lower = {opt.lower() for opt in menu_options}
            for vision_opt in vision_menu_options:
                if vision_opt.lower() not in existing_lower:
                    menu_options.append(vision_opt)
                    print(f"[Turn {turn + 1}] 👁️ Added vision-detected option: {vision_opt}")
        
        if menu_options:
            print(f"[Turn {turn + 1}] Menu options ({len(menu_options)}): {menu_options[:5]}")
            progress_made = True  # Having menu options means bot is responding
        
        # LOOP DETECTION: Check if we're about to repeat the same action
        is_yes_no_confirmation = detect_yes_no_confirmation(bot_response)
        if is_yes_no_confirmation:
            print(f"[Turn {turn + 1}] Detected Yes/No confirmation question")
        
        # Ask LLM for decision - pass action history for context
        decision = analyze_and_decide(
            current_message, 
            bot_response, 
            menu_options,
            action_history=action_history  # Pass history for loop detection
        )
        print(f"[Turn {turn + 1}] LLM Decision: {decision.action} - {decision.reason}")
        
        # LOOP DETECTION: If LLM wants to click the same option as last time,
        # and this is a confirmation question, switch to clicking "Yes" instead
        if decision.action == "CLICK_MENU" and decision.menu_choice:
            if decision.menu_choice.lower() == last_menu_choice.lower():
                consecutive_same_choice += 1
                print(f"[Turn {turn + 1}] ⚠️ LOOP DETECTED: Would click same option ({consecutive_same_choice} times)")
                
                if consecutive_same_choice >= 1 and is_yes_no_confirmation:
                    # Look for "Yes" in menu options and switch to it
                    yes_option = next((opt for opt in menu_options if opt.lower() in ['yes', 'yes, continue', 'confirm']), None)
                    if yes_option:
                        print(f"[Turn {turn + 1}] 🔄 Auto-switching to confirmation: '{yes_option}'")
                        decision = AdaptiveDecision(
                            action="CLICK_MENU",
                            menu_choice=yes_option,
                            reason="Auto-confirmed to break loop (detected repeated selection)",
                            score=decision.score,
                            intent_identified=True,
                            flow_completed=False
                        )
                    else:
                        # No explicit Yes button found - try clicking "Yes" directly
                        print(f"[Turn {turn + 1}] 🔄 Trying direct 'Yes' click")
                        decision = AdaptiveDecision(
                            action="CLICK_MENU",
                            menu_choice="Yes",
                            reason="Auto-confirmed with 'Yes' to break loop",
                            score=decision.score,
                            intent_identified=True,
                            flow_completed=False
                        )
            else:
                # Different option, reset counter
                consecutive_same_choice = 0
        
        # Update last menu choice for next iteration
        if decision.action == "CLICK_MENU" and decision.menu_choice:
            last_menu_choice = decision.menu_choice
        
        # Record action with menu_choice for history tracking
        action_history.append({
            "turn": turn + 1,
            "message": current_message,
            "response": bot_response[:200] if bot_response else "",
            "action": decision.action,
            "menu_choice": decision.menu_choice if decision.action == "CLICK_MENU" else "",
            "reason": decision.reason,
            "progress": progress_made
        })
        
        # Execute decision
        if decision.action == "PASS":
            final_decision = decision
            print(f"[Turn {turn + 1}] ✅ PASS - Flow completed")
            break
            
        elif decision.action == "FAIL":
            final_decision = decision
            print(f"[Turn {turn + 1}] ❌ FAIL - {decision.reason}")
            break
            
        elif decision.action == "CLICK_MENU":
            if decision.menu_choice:
                menu_clicks.append(decision.menu_choice)
                clicked = click_menu_option(page, decision.menu_choice)
                if clicked:
                    # Wait longer after menu click for bot to fully respond with new options
                    # The bot may show "My credit card" / "My banking account" options after this
                    page.wait_for_timeout(5000)  # Increased from 3000
                    # Continue loop to check response after click
                    current_message = ""  # Will be set by next bot response
                else:
                    print(f"[Turn {turn + 1}] Could not click menu option")
                    # Don't fail immediately - try alternative approach
                    if turn < max_turns - 1:
                        current_message = f"I want to check my {category.replace('_', ' ')}"
                        print(f"[Turn {turn + 1}] Trying alternative: {current_message}")
                    else:
                        final_decision = AdaptiveDecision(
                            action="FAIL",
                            reason="Could not click menu option",
                            score=decision.score
                        )
                        break
            else:
                # No menu choice provided, treat as FAIL
                final_decision = decision
                break
                
        elif decision.action == "CONTINUE":
            if decision.follow_up:
                current_message = decision.follow_up
            else:
                # No follow-up provided - generate context-aware follow-up
                context_follow_ups = {
                    "account_balance": "my credit card balance",
                    "transactions": "my recent transactions",
                    "payments": "make a payment",
                    "card_issues": "report a problem with my card",
                }
                current_message = context_follow_ups.get(category, "help me with my account")
                print(f"[Turn {turn + 1}] Using context-aware follow-up: {current_message}")
        else:
            # Unknown action
            final_decision = AdaptiveDecision(
                action="FAIL",
                reason=f"Unknown action: {decision.action}",
                score=0
            )
            break
    
    # Calculate metrics
    end_time = time.time()
    latency_ms = int((end_time - start_time) * 1000)
    
    # Handle max turns with partial success tracking
    if final_decision is None:
        if progress_made and best_score >= 5.0:
            # Partial success - we made progress but didn't complete
            final_decision = AdaptiveDecision(
                action="PARTIAL",
                reason=f"Max turns reached but progress made (best score: {best_score})",
                score=best_score,
                intent_identified=True,
                flow_completed=False
            )
            status = "partial"
        else:
            final_decision = AdaptiveDecision(
                action="FAIL",
                reason="Max turns reached without resolution",
                score=max(3.0, best_score)
            )
            status = "fail"
    else:
        status = "pass" if final_decision.action == "PASS" else "fail"
    
    # Use best response if no valid response in final decision
    final_response = action_history[-1]["response"] if action_history else ""
    if not final_response or is_invalid_response(final_response):
        final_response = best_response
    
    # Save to database
    log = ConversationLog(
        test_run_id=test_run_id,
        utterance=utterance,
        bot_response=final_response,
        latency_ms=latency_ms,
        status=status,
        category=category,
        timestamp=get_local_now(),
        overall_score=final_decision.score,
        llm_feedback=final_decision.reason,
        # Adaptive testing fields
        turns=turn + 1,
        menu_clicks=json.dumps(menu_clicks),
        intent_identified=final_decision.intent_identified,
        flow_completed=final_decision.flow_completed,
        action_history=json.dumps(action_history)
    )
    session.add(log)
    session.commit()
    
    print(f"\nResult: {status.upper()} | Turns: {turn + 1} | Score: {final_decision.score}")
    
    return {
        "status": status,
        "turns": turn + 1,
        "score": final_decision.score,
        "latency_ms": latency_ms,
        "intent_identified": final_decision.intent_identified,
        "flow_completed": final_decision.flow_completed,
        "progress_made": progress_made
    }

