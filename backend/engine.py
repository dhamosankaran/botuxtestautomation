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
from models import TestRun, ConversationLog, Credentials, ChatbotConfig, LoginSelectors
from llm_evaluator import evaluate_response, EvaluationResult, analyze_and_decide, AdaptiveDecision
from utterances import get_category_for_utterance, get_expected_intent

# Playwright configuration from environment
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
PLAYWRIGHT_SLOW_MO = int(os.getenv("PLAYWRIGHT_SLOW_MO", "200"))
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "60000"))
print(f"[ENGINE CONFIG] Headless={PLAYWRIGHT_HEADLESS}, SlowMo={PLAYWRIGHT_SLOW_MO}ms, Timeout={PLAYWRIGHT_TIMEOUT}ms")

# Citi credentials from .env (fallback if not provided in request)
CITI_USER_ID = os.getenv("CITI_USER_ID", "")
CITI_PASSWORD = os.getenv("CITI_PASSWORD", "")

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
                test_run.completed_at = datetime.utcnow()
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
                        # Skip if it's the user's utterance or empty
                        if text and text != utterance and len(text) > 5:
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
                        if text and text != utterance and len(text) > 5:
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
            timestamp=datetime.utcnow(),
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
            timestamp=datetime.utcnow()
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
    test_run.completed_at = datetime.utcnow()
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

def extract_menu_options(page: Page) -> List[str]:
    """
    Extract clickable menu options from WITHIN the chat widget ONLY.
    Ignores all dashboard elements completely.
    """
    menu_options = []
    
    # First, find the chat widget container
    # The Citi Bot chat is typically in a specific container with identifiable classes
    chat_container_selectors = [
        "[class*='citi-bot']",
        "[class*='chat-widget']",
        "[class*='chat-container']",
        "[class*='chatbot']",
        "[class*='chat-window']",
        "[class*='messaging']",
        "[id*='chat']",
        "[aria-label*='chat' i]",
        # Look for container that has the message input
        ":has(input[placeholder*='message' i])",
        ":has(textarea[placeholder*='message' i])",
    ]
    
    chat_container = None
    for selector in chat_container_selectors:
        try:
            container = page.locator(selector).first
            if container.is_visible(timeout=500):
                chat_container = container
                print(f"Found chat container: {selector}")
                break
        except Exception:
            continue
    
    if not chat_container:
        print("Could not find chat widget container - returning empty menu options")
        return []
    
    # Now search for menu options ONLY within the chat container
    # These are response option buttons the bot presents
    within_chat_selectors = [
        "button",
        "[role='button']",
        "[class*='option']",
        "[class*='choice']",
        "[class*='chip']",
        "[class*='quick-reply']",
        "[class*='suggestion']",
    ]
    
    # Skip keywords - these are NOT valid chat menu options
    skip_keywords = [
        "send", "submit", "close", "minimize", "x", 
        "view", "go to", "open", "navigate", "see more", "learn more",
        "sign off", "help", "menu",
    ]
    
    for selector in within_chat_selectors:
        try:
            # Search ONLY within the chat container
            elements = chat_container.locator(selector)
            count = elements.count()
            for i in range(min(count, 10)):
                try:
                    el = elements.nth(i)
                    if el.is_visible(timeout=300):
                        text = (el.text_content() or "").strip()
                        text_lower = text.lower()
                        
                        # Skip if too short, too long, empty, or contains skip keywords
                        if len(text) < 3 or len(text) > 60:
                            continue
                        if any(kw in text_lower for kw in skip_keywords):
                            continue
                        # Skip transaction-like text (has dollar amounts with dates)
                        if "$" in text and ("posted" in text_lower or "20" in text):
                            continue
                        
                        if text not in menu_options:
                            menu_options.append(text)
                except Exception:
                    continue
        except Exception:
            continue
    
    # Filter to keep only likely valid options (credit card names, action terms)
    valid_patterns = ["card", "balance", "payment", "citi", "strata", "cash", "double"]
    if menu_options:
        # If we have many options, filter to those matching valid patterns
        filtered = [opt for opt in menu_options if any(p in opt.lower() for p in valid_patterns)]
        if filtered:
            menu_options = filtered
    
    print(f"Extracted {len(menu_options)} menu options from chat widget: {menu_options[:3]}...")
    return menu_options


def click_menu_option(page: Page, option_text: str) -> bool:
    """
    Click a menu option by its text WITHIN the chat widget only.
    Returns True if clicked successfully.
    """
    try:
        # First, find the chat widget container
        chat_container_selectors = [
            "[class*='citi-bot']",
            "[class*='chat-widget']",
            "[class*='chat-container']",
            "[class*='chatbot']",
            "[class*='chat-window']",
            ":has(input[placeholder*='message' i])",
        ]
        
        chat_container = None
        for selector in chat_container_selectors:
            try:
                container = page.locator(selector).first
                if container.is_visible(timeout=500):
                    chat_container = container
                    break
            except Exception:
                continue
        
        if not chat_container:
            print(f"Could not find chat container to click menu option")
            # Fall back to page-wide search
            chat_container = page
        
        # Try to find and click the button within chat container
        selectors = [
            f"button:has-text('{option_text}')",
            f"[role='button']:has-text('{option_text}')",
        ]
        
        for selector in selectors:
            try:
                el = chat_container.locator(selector).first
                if el.is_visible(timeout=1000):
                    el.click(force=True)
                    print(f"Clicked menu option in chat: '{option_text}'")
                    return True
            except Exception:
                continue
        
        # JavaScript fallback - scope to chat container
        result = page.evaluate(f"""
            () => {{
                // Find chat container first
                const chatContainers = document.querySelectorAll('[class*="chat"], [class*="citi-bot"]');
                for (const container of chatContainers) {{
                    const buttons = container.querySelectorAll('button, [role="button"]');
                    for (const btn of buttons) {{
                        if (btn.textContent?.includes('{option_text}')) {{
                            btn.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }}
        """)
        if result:
            print(f"Clicked menu option via JS in chat: '{option_text}'")
            return True
            
    except Exception as e:
        print(f"Failed to click menu option '{option_text}': {e}")
    
    return False


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
        
        # Wait for response - give more time
        page.wait_for_timeout(3000)
        
        # Capture response with better selectors
        response_selectors = [
            "[class*='message-content']",
            "[class*='chat-message']",
            "[class*='bot-message']",
            "[class*='assistant-message']",
            "[class*='bubble']",
            "[class*='response']",
            "[class*='msg-text']",
        ]
        
        bot_response = ""
        for attempt in range(15):  # Try for ~7.5 seconds
            # Try to get messages
            try:
                all_messages = page.query_selector_all("[class*='message']")
                if all_messages and len(all_messages) > 0:
                    for msg in reversed(all_messages):
                        text = (msg.text_content() or "").strip()
                        if text and text != message and len(text) > 5:
                            bot_response = text
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
                        text = (latest.text_content() or "").strip()
                        if text and text != message and len(text) > 5:
                            bot_response = text
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
    
    for turn in range(max_turns):
        print(f"\n[Turn {turn + 1}] Sending: {current_message[:40]}...")
        
        # Send message and get response
        bot_response = send_message_and_get_response(page, current_message)
        print(f"[Turn {turn + 1}] Bot: {bot_response[:100]}...")
        
        # Extract menu options
        menu_options = extract_menu_options(page)
        if menu_options:
            print(f"[Turn {turn + 1}] Menu options: {menu_options}")
        
        # Ask LLM for decision
        decision = analyze_and_decide(current_message, bot_response, menu_options)
        print(f"[Turn {turn + 1}] LLM Decision: {decision.action} - {decision.reason}")
        
        # Record action
        action_history.append({
            "turn": turn + 1,
            "message": current_message,
            "response": bot_response[:200],
            "action": decision.action,
            "reason": decision.reason
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
                    page.wait_for_timeout(2000)
                    # Continue loop to check response after click
                    current_message = ""  # Will be set by next bot response
                else:
                    print(f"[Turn {turn + 1}] Could not click menu option")
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
                # No follow-up provided, mark as FAIL
                final_decision = AdaptiveDecision(
                    action="FAIL",
                    reason="No follow-up provided",
                    score=decision.score
                )
                break
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
    
    if final_decision is None:
        final_decision = AdaptiveDecision(
            action="FAIL",
            reason="Max turns reached without resolution",
            score=3.0
        )
    
    # Determine status
    status = "pass" if final_decision.action == "PASS" else "fail"
    
    # Save to database
    category = get_category_for_utterance(utterance)
    log = ConversationLog(
        test_run_id=test_run_id,
        utterance=utterance,
        bot_response=action_history[-1]["response"] if action_history else "",
        latency_ms=latency_ms,
        status=status,
        category=category,
        timestamp=datetime.utcnow(),
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
        "flow_completed": final_decision.flow_completed
    }

