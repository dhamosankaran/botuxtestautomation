"""MCP Browser Server — Playwright abstraction for chatbot interaction.

Wraps Playwright async API. Implements all three spec guardrails:
- Guardrail 2: Composite wait strategy (typing bubble → text stabilization)
- Guardrail 3: Iframe traversal with WidgetContext frame scoping

All browser I/O is async. Never use time.sleep(); always asyncio.sleep().
"""
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.async_api import Frame, Page, Playwright

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Selector libraries (common enterprise chat widgets)
# ---------------------------------------------------------------------------

_INPUT_SELECTORS = [
    "input[placeholder*='message' i]",
    "textarea[placeholder*='message' i]",
    "input[placeholder*='type' i]",
    "textarea[placeholder*='type' i]",
    "input[aria-label*='message' i]",
    "[contenteditable='true']",
    "[data-testid*='input']",
    "[data-testid*='message-input']",
    ".chat-input",
    "#chat-input",
]

_SUBMIT_SELECTORS = [
    "button[type='submit']",
    "button[aria-label*='send' i]",
    "button[data-testid*='send']",
    "[data-testid*='submit']",
    ".send-button",
    "#send-button",
]

_MESSAGE_SELECTORS = [
    ".message-list",
    "#message-list",
    "[class*='message-list']",
    "[class*='chat-list']",
    "[class*='conversation']",
    "[data-testid*='message-list']",
    "[class*='chat-message']",
    "[class*='bot-message']",
    "[class*='assistant-message']",
    "[class*='agent-message']",
    "[data-testid*='bot-message']",
]

_TYPING_SELECTORS = [
    ".typing-indicator",
    "[class*='typing']",
    "[class*='loading']",
    ".dot-animation",
    "[aria-label*='typing' i]",
    "[class*='is-typing']",
]

_WIDGET_SELECTORS = [
    "[data-testid='chat-widget']",
    "#chat-widget",
    ".chat-widget",
    "iframe[title*='chat' i]",
    "iframe[src*='chat']",
    "iframe[src*='widget']",
    "[id*='intercom']",
    "[id*='drift']",
    "[id*='zendesk']",
    "[id*='liveperson']",
    ".chat-launcher",
    ".chat-button",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class WidgetContext:
    """Frame + selector context for a detected chat widget.

    All subsequent MCP calls MUST execute within ``frame`` to handle
    cross-origin iframes correctly (Guardrail 3).
    """

    frame: Frame
    input_selector: str
    messages_selector: str
    submit_method: str  # "enter_key" | "button_click"
    submit_selector: Optional[str]  # Populated when submit_method == "button_click"


@dataclass
class ChatMessage:
    """A single parsed message from the chat widget."""

    sender: str  # "bot" | "user"
    text: str
    timestamp_captured: str
    raw_html: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal: retry with exponential backoff
# ---------------------------------------------------------------------------


async def _retry(coro_fn, *args, retries: int = 3, base_delay: float = 1.0,
                 label: str = "op", **kwargs):
    """Execute an async callable with exponential backoff.

    Args:
        coro_fn: Async callable.
        retries: Max attempts.
        base_delay: Base wait in seconds (doubles each retry: 1s → 2s → 4s).
        label: Name for log messages.

    Returns:
        Result of successful call.

    Raises:
        Exception: Last exception after all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                delay = base_delay ** attempt
                logger.warning("%s attempt %d/%d failed: %s — retry in %.1fs",
                               label, attempt, retries, exc, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("%s failed after %d attempts: %s", label, retries, exc)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Core browser functions
# ---------------------------------------------------------------------------


async def navigate_to_url(page: Page, url: str) -> None:
    """Navigate to ``url`` and wait for DOM content to load.

    Args:
        page: Playwright Page.
        url: Target URL string.
    """
    async def _nav():
        await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
        logger.info("Navigated to %s", url)

    await _retry(_nav, label=f"navigate({url})")


async def click_element(page: Page, selector: str,
                        frame: Optional[Frame] = None) -> None:
    """Click a DOM element.

    Args:
        page: Playwright Page.
        selector: CSS selector for the target element.
        frame: Optional frame scope (defaults to main frame).
    """
    ctx = frame or page

    async def _click():
        await ctx.click(selector, timeout=5_000)
        logger.debug("Clicked: %s", selector)

    await _retry(_click, label=f"click({selector})")


async def type_text(page: Page, selector: str, text: str,
                    frame: Optional[Frame] = None) -> None:
    """Fill an input field with ``text``.

    Args:
        page: Playwright Page.
        selector: CSS selector for the input.
        text: Text to type.
        frame: Optional frame scope.
    """
    ctx = frame or page

    async def _fill():
        await ctx.fill(selector, text, timeout=5_000)
        logger.debug("Typed into %s", selector)

    await _retry(_fill, label=f"type_text({selector})")


async def wait_for_selector(page: Page, selector: str,
                             timeout_ms: int = 10_000,
                             frame: Optional[Frame] = None) -> bool:
    """Wait for a selector to be visible.

    Args:
        page: Playwright Page.
        selector: CSS selector to wait for.
        timeout_ms: Max wait in milliseconds.
        frame: Optional frame scope.

    Returns:
        True when element is visible.
    """
    ctx = frame or page

    async def _wait():
        await ctx.wait_for_selector(selector, state="visible", timeout=timeout_ms)
        return True

    return await _retry(_wait, label=f"wait_for({selector})")


async def get_dom_snapshot(page: Page) -> str:
    """Return the full page HTML for debugging.

    Args:
        page: Playwright Page.

    Returns:
        HTML string, empty on failure.
    """
    try:
        html: str = await page.content()
        logger.debug("DOM snapshot: %d chars", len(html))
        return html
    except Exception as exc:
        logger.error("DOM snapshot failed: %s", exc)
        return ""


async def extract_visible_text(page: Page, selector: Optional[str] = None,
                                frame: Optional[Frame] = None) -> str:
    """Return visible text content from the page or a scoped element.

    Args:
        page: Playwright Page.
        selector: Optional CSS selector to scope extraction.
        frame: Optional frame scope.

    Returns:
        Text string, empty on failure.
    """
    ctx = frame or page
    try:
        if selector:
            el = await ctx.query_selector(selector)
            return (await el.inner_text()).strip() if el else ""
        return (await page.inner_text("body")).strip()
    except Exception as exc:
        logger.error("extract_visible_text failed: %s", exc)
        return ""


async def capture_screenshot(page: Page, path: str) -> None:
    """Save a full-page screenshot. Non-fatal on failure.

    Args:
        page: Playwright Page.
        path: Destination file path (PNG).
    """
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=path, full_page=True)
        logger.info("Screenshot saved: %s", path)
    except Exception as exc:
        logger.error("Screenshot failed (%s): %s", path, exc)


# ---------------------------------------------------------------------------
# Internal: probe a single frame for chat widget elements
# ---------------------------------------------------------------------------


async def _probe_frame(frame: Frame) -> Optional[WidgetContext]:
    """Scan a Playwright Frame for an input + message container pair.

    Args:
        frame: Playwright Frame to inspect.

    Returns:
        WidgetContext if a chat widget is found, otherwise None.
    """
    input_sel: Optional[str] = None
    for sel in _INPUT_SELECTORS:
        try:
            el = await frame.query_selector(sel)
            if el and await el.is_visible():
                input_sel = sel
                break
        except Exception:
            continue

    if not input_sel:
        return None

    msg_sel = "body"
    for sel in _MESSAGE_SELECTORS:
        try:
            el = await frame.query_selector(sel)
            if el:
                msg_sel = sel
                break
        except Exception:
            continue

    submit_sel: Optional[str] = None
    submit_method = "enter_key"
    for sel in _SUBMIT_SELECTORS:
        try:
            el = await frame.query_selector(sel)
            if el and await el.is_visible():
                submit_sel = sel
                submit_method = "button_click"
                break
        except Exception:
            continue

    return WidgetContext(
        frame=frame,
        input_selector=input_sel,
        messages_selector=msg_sel,
        submit_method=submit_method,
        submit_selector=submit_sel,
    )


# ---------------------------------------------------------------------------
# Chatbot function: widget detection (Guardrail 3 — iframe traversal)
# ---------------------------------------------------------------------------


async def detect_chat_widget(page: Page,
                              scenario_selectors: Optional[list[str]] = None
                              ) -> Optional[WidgetContext]:
    """Find the chat widget, checking the main frame then all iframes.

    Returns a WidgetContext that carries the correct Playwright Frame
    reference. All subsequent calls MUST use this frame to avoid silent
    selector failures in cross-origin iframes (Guardrail 3).

    Args:
        page: Playwright Page.
        scenario_selectors: Primary + fallback selectors from scenario YAML,
            tried first in the main frame.

    Returns:
        WidgetContext on success, None if no widget found.
    """
    # 1. Scenario-defined selectors — main frame first
    if scenario_selectors:
        for sel in scenario_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    ctx = await _probe_frame(page.main_frame)
                    if ctx:
                        logger.info("Widget found via scenario selector: %s", sel)
                        return ctx
            except Exception:
                continue

    # 2. Common patterns in main frame
    ctx = await _probe_frame(page.main_frame)
    if ctx:
        logger.info("Widget found in main frame")
        return ctx

    # 3. Iterate all iframes (Guardrail 3)
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            ctx = await _probe_frame(frame)
            if ctx:
                logger.info("Widget found in iframe: %s", frame.url)
                return ctx
        except Exception as exc:
            logger.debug("Error probing iframe %s: %s", frame.url, exc)

    logger.warning("No chat widget found on %s", page.url)
    return None


# ---------------------------------------------------------------------------
# Chatbot function: composite wait strategy (Guardrail 2)
# ---------------------------------------------------------------------------


async def wait_for_bot_response(frame: Frame, messages_selector: str,
                                  timeout_ms: int = 10_000,
                                  stabilization_ms: int = 500,
                                  poll_interval_ms: int = 100) -> bool:
    """Wait until the bot has finished responding.

    Composite strategy (Guardrail 2):
    1. Wait for typing indicator to appear.
    2. Wait for typing indicator to disappear.
    3. Capture message text.
    4. Wait stabilization_ms.
    5. Re-capture; if text changed, reset the stabilization timer.
    6. Return only when text is stable for the full stabilization window.

    Does NOT use networkidle (unreliable with CSS animations).

    Args:
        frame: Playwright Frame containing the widget.
        messages_selector: CSS selector for the message container.
        timeout_ms: Hard deadline in milliseconds.
        stabilization_ms: Required stable period in milliseconds.
        poll_interval_ms: Polling frequency in milliseconds.

    Returns:
        True when response is stable, False on timeout.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_ms / 1000.0

    # Steps 1 & 2: typing indicator lifecycle
    for sel in _TYPING_SELECTORS:
        try:
            await frame.wait_for_selector(sel, state="visible", timeout=2_000)
            logger.debug("Typing indicator appeared: %s", sel)
            await frame.wait_for_selector(sel, state="hidden", timeout=timeout_ms)
            logger.debug("Typing indicator gone: %s", sel)
            break
        except Exception:
            continue

    # Steps 3–6: text stabilization loop
    async def _snapshot() -> str:
        try:
            el = await frame.query_selector(messages_selector)
            return await el.inner_text() if el else ""
        except Exception:
            return ""

    last_text = await _snapshot()
    stable_since = loop.time()

    while loop.time() < deadline:
        await asyncio.sleep(poll_interval_ms / 1000.0)
        current = await _snapshot()
        if current != last_text:
            last_text = current
            stable_since = loop.time()
            logger.debug("Response still streaming…")
        elif loop.time() - stable_since >= stabilization_ms / 1000.0:
            logger.debug("Response stabilized")
            return True

    logger.warning("wait_for_bot_response timed out after %dms", timeout_ms)
    return False


# ---------------------------------------------------------------------------
# Chatbot function: send message
# ---------------------------------------------------------------------------


async def send_chat_message(text: str, widget_ctx: WidgetContext) -> None:
    """Type ``text`` into the chat input and submit it.

    Handles Enter-key and button-click submission automatically based on
    the submit_method discovered in detect_chat_widget().

    Args:
        text: Message to send.
        widget_ctx: Context returned by detect_chat_widget().
    """
    frame = widget_ctx.frame

    async def _send():
        await frame.fill(widget_ctx.input_selector, text, timeout=5_000)
        await asyncio.sleep(0.1)
        if widget_ctx.submit_method == "button_click" and widget_ctx.submit_selector:
            await frame.click(widget_ctx.submit_selector, timeout=5_000)
            logger.debug("Submitted via button click")
        else:
            await frame.press(widget_ctx.input_selector, "Enter")
            logger.debug("Submitted via Enter key")
        logger.info("Sent: %s", text[:80])

    await _retry(_send, label="send_chat_message")


# ---------------------------------------------------------------------------
# Chatbot function: extract messages
# ---------------------------------------------------------------------------


async def extract_chat_messages(widget_ctx: WidgetContext) -> list[ChatMessage]:
    """Parse the chat widget DOM and return structured message objects.

    Args:
        widget_ctx: Context returned by detect_chat_widget().

    Returns:
        List of ChatMessage ordered by DOM position.
    """
    from datetime import datetime, timezone

    frame = widget_ctx.frame
    messages: list[ChatMessage] = []
    now = datetime.now(timezone.utc).isoformat()

    try:
        query = (
            f"{widget_ctx.messages_selector} [class*='message'], "
            f"{widget_ctx.messages_selector} [class*='msg'], "
            f"{widget_ctx.messages_selector} [role='listitem']"
        )
        elements = await frame.query_selector_all(query)
        if not elements:
            elements = await frame.query_selector_all(
                f"{widget_ctx.messages_selector} > *"
            )

        for el in elements:
            try:
                text = (await el.inner_text()).strip()
                if not text:
                    continue
                html = await el.inner_html()
                cls = await el.get_attribute("class") or ""
                cls_lower = cls.lower()
                # Explicit bot-class check takes priority over user-class check
                if any(k in cls_lower for k in ("bot-message", "assistant-message",
                                                 "agent-message")):
                    sender = "bot"
                elif any(k in cls_lower for k in ("user", "customer", "human", "self")):
                    sender = "user"
                else:
                    sender = "bot"
                messages.append(ChatMessage(sender=sender, text=text,
                                            timestamp_captured=now, raw_html=html))
            except Exception as exc:
                logger.debug("Skipping malformed message element: %s", exc)
    except Exception as exc:
        logger.error("extract_chat_messages failed: %s", exc)

    logger.debug("Extracted %d messages", len(messages))
    return messages


# ---------------------------------------------------------------------------
# Pre-steps: generic page automation before widget detection
# ---------------------------------------------------------------------------


async def execute_pre_steps(page: Page, steps: list[dict]) -> None:
    """Execute a sequence of pre-steps before chatbot widget detection.

    Supported step actions:
        navigate        — go to a URL
        click           — click a CSS selector
        fill            — fill an input field
        wait_for_selector — wait for an element to appear
        wait            — sleep for a fixed duration (ms)
        login           — high-level Citi login helper (reads env vars)

    Args:
        page: Playwright Page.
        steps: List of step dicts from scenario YAML ``pre_steps`` section.
    """
    import os

    for i, step in enumerate(steps):
        action = step.get("action", "")
        label = step.get("label", f"step_{i + 1}")
        logger.info("Pre-step [%s]: %s", label, action)

        try:
            if action == "navigate":
                url = step["url"]
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                logger.info("Navigated to %s", url)

            elif action == "click":
                selector = step["selector"]
                await page.wait_for_selector(selector, state="visible", timeout=15_000)
                await page.click(selector, timeout=10_000)
                logger.info("Clicked: %s", selector)

            elif action == "fill":
                selector = step["selector"]
                value = step.get("value", "")
                # Support env var substitution: ${ENV_VAR_NAME}
                if value.startswith("${") and value.endswith("}"):
                    env_key = value[2:-1]
                    value = os.environ.get(env_key, "")
                    if not value:
                        logger.warning("Env var %s not set for fill step", env_key)
                await page.wait_for_selector(selector, state="visible", timeout=15_000)
                await page.fill(selector, value, timeout=10_000)
                logger.info("Filled: %s", selector)

            elif action == "wait_for_selector":
                selector = step["selector"]
                state = step.get("state", "visible")
                timeout = int(step.get("timeout_ms", 15_000))
                await page.wait_for_selector(selector, state=state, timeout=timeout)
                logger.info("Selector ready: %s", selector)

            elif action == "wait":
                ms = int(step.get("ms", 1000))
                await asyncio.sleep(ms / 1000.0)
                logger.info("Waited %dms", ms)

            elif action == "login":
                # High-level login: reads credentials from env, handles submit
                user_id = os.environ.get("CITI_USER_ID", step.get("user_id", ""))
                password = os.environ.get("CITI_PASSWORD", step.get("password", ""))
                user_selector = step.get("user_selector", "#userId")
                pass_selector = step.get("pass_selector", "#password")
                submit_selector = step.get("submit_selector", "button[type='submit']")

                if not user_id or not password:
                    raise ValueError(
                        "CITI_USER_ID and CITI_PASSWORD must be set in backend/.env "
                        "for the 'login' pre-step action"
                    )

                # Fill user ID
                await page.wait_for_selector(user_selector, state="visible", timeout=20_000)
                await page.fill(user_selector, user_id, timeout=10_000)
                logger.info("Filled user ID field")

                # Fill password (if on same page)
                try:
                    await page.wait_for_selector(pass_selector, state="visible", timeout=5_000)
                    await page.fill(pass_selector, password, timeout=10_000)
                    logger.info("Filled password field")
                except Exception:
                    # Some sites (incl. Citi) show user/pass on separate pages
                    logger.info("Password field not yet visible — submitting user ID first")
                    await page.click(submit_selector, timeout=10_000)
                    await page.wait_for_selector(pass_selector, state="visible", timeout=20_000)
                    await page.fill(pass_selector, password, timeout=10_000)
                    logger.info("Filled password on second page")

                # Final submit
                await page.click(submit_selector, timeout=10_000)
                logger.info("Submitted login form")

                # Wait for post-login navigation
                post_url = step.get("wait_for_url_contains", "")
                wait_selector = step.get("wait_for_selector", "")
                if post_url:
                    await page.wait_for_url(f"**{post_url}**", timeout=30_000)
                    logger.info("Login confirmed — URL contains: %s", post_url)
                elif wait_selector:
                    await page.wait_for_selector(wait_selector, state="visible", timeout=30_000)
                    logger.info("Login confirmed — element visible: %s", wait_selector)
                else:
                    await asyncio.sleep(3)
                    logger.info("Login submitted — waiting 3s for redirect")

            else:
                logger.warning("Unknown pre-step action '%s' — skipping", action)

        except Exception as exc:
            if step.get("fallback_steps"):
                logger.info("Pre-step '%s' failed, executing fallback steps", label)
                await execute_pre_steps(page, step["fallback_steps"])
                continue
            if step.get("optional"):
                logger.info("Optional pre-step '%s' failed, skipping: %s", label, exc)
                continue
            raise RuntimeError(
                f"Pre-step '{label}' ({action}) failed: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Browser lifecycle
# ---------------------------------------------------------------------------


async def launch_browser(playwright: Playwright, headless: bool = True,
                          stealth: bool = True,
                          viewport: Optional[dict] = None,
                          chrome_user_data_dir: Optional[str] = None,
                          slow_mo: int = 0) -> tuple:
    """Launch Chromium — normal mode or persistent Chrome profile mode.

    When ``chrome_user_data_dir`` is set, launches using
    ``launch_persistent_context``, which loads the user's real Chrome
    profile complete with cookies and session state. This is the recommended
    approach for sites (e.g. Citi) that use bot detection or MFA, since the
    existing authenticated session bypasses both.

    Args:
        playwright: Playwright instance from async_playwright().
        headless: Run without a visible window.
        stealth: Apply playwright-stealth patches (normal mode only).
        viewport: Dict with 'width' and 'height'.
        chrome_user_data_dir: Absolute path to a Chrome user data directory.
            If set, uses persistent context mode with the real Chrome profile.
            On macOS the default Chrome profile is at:
            ~/Library/Application Support/Google/Chrome
        slow_mo: Milliseconds to slow down each Playwright operation
            (helps defeat timing-based bot detection). Default 0.

    Returns:
        Tuple of (browser_or_none, context, page).
        In persistent context mode, browser is None (context IS the browser).
    """
    import os
    vp = viewport or {"width": 1280, "height": 720}

    if chrome_user_data_dir:
        # ── Persistent context mode (real Chrome profile) ──────────────────
        expanded = os.path.expanduser(chrome_user_data_dir)
        if not os.path.isdir(expanded):
            raise FileNotFoundError(
                f"chrome_user_data_dir not found: {expanded}\n"
                "On macOS: ~/Library/Application Support/Google/Chrome\n"
                "On Windows: %LOCALAPPDATA%/Google/Chrome/User Data"
            )

        # Check for Chrome lock to prevent "profile in use" crashes
        lock_file = os.path.join(expanded, "SingletonLock")
        if os.path.lexists(lock_file):  # lexists catches broken symlinks on macOS
            logger.warning("Chrome profile is locked! Attempting safe profile clone...")
            import shutil
            import tempfile
            
            # Create a temporary directory to host the cloned profile
            temp_dir = tempfile.mkdtemp(prefix="bottest_chrome_")
            logger.info("Cloning Chrome profile to %s", temp_dir)
            
            # We copy just the main profile ('Default') and specific essential folders
            # to avoid copying gigabytes of Cache and locking up.
            def ignore_caches(dir_path, contents):
                # Ignore locking files and large cache directories
                ignores = [
                    "SingletonLock", "SingletonCookie", "SingletonSocket", 
                    "Cache", "Code Cache", "GPUCache", "Media Cache", 
                    "Service Worker", "Crashpad", "Safe Browsing"
                ]
                return [c for c in contents if c in ignores]
                
            try:
                # Basic Chrome structure requires the Local State
                local_state = os.path.join(expanded, "Local State")
                if os.path.exists(local_state):
                    shutil.copy2(local_state, os.path.join(temp_dir, "Local State"))
                    
                # Copy the Default profile
                default_profile = os.path.join(expanded, "Default")
                target_default = os.path.join(temp_dir, "Default")
                if os.path.exists(default_profile):
                    shutil.copytree(default_profile, target_default, ignore=ignore_caches, dirs_exist_ok=True)
                
                # Update our launch target to the temp clone
                expanded = temp_dir
                logger.info("Chrome profile clone successful")
            except Exception as e:
                logger.error("Failed to clone Chrome profile: %s", e)
                logger.error("Please QUITE CHROME completely and try again.")
                raise

        logger.info("Launching Chrome with persistent profile: %s", expanded)
        chrome_exe = (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
        if not os.path.exists(chrome_exe):
            chrome_exe = None  # type: ignore[assignment]

        context = await playwright.chromium.launch_persistent_context(
            expanded,
            headless=headless,
            executable_path=chrome_exe,
            viewport=vp,
            slow_mo=slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        logger.info("Persistent context launched — session cookies loaded")
        return None, context, page

    # ── Normal (ephemeral) Chromium mode ──────────────────────────────────
    browser = await playwright.chromium.launch(
        headless=headless,
        slow_mo=slow_mo,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(
        viewport=vp,
        java_script_enabled=True,
    )
    page = await context.new_page()

    if stealth:
        try:
            from playwright_stealth import Stealth
            await Stealth().apply_stealth_async(page)
            logger.info("Stealth mode applied")
        except ImportError:
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
                logger.info("Stealth mode (legacy) applied")
            except ImportError:
                logger.warning("playwright-stealth not installed; skipping stealth")

    return browser, context, page

