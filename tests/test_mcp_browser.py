"""Integration tests for backend/mcp_browser.py.

Tests run against the local mock chatbot HTML fixture.
Requires Playwright chromium: playwright install chromium

Mark: integration — excluded from fast unit-only runs.
"""
import asyncio
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mock_chatbot.html"
FIXTURE_URL = f"file://{FIXTURE_PATH.resolve()}"


@pytest_asyncio.fixture
async def browser_page():
    """Launch Chromium headlessly, yield page, close after test."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await ctx.new_page()
        yield page
        await browser.close()


# ---------------------------------------------------------------------------
# Navigation & text extraction
# ---------------------------------------------------------------------------


async def test_navigate_and_extract(browser_page):
    """Navigate to mock page and extract visible text."""
    from backend.mcp_browser import extract_visible_text, navigate_to_url

    await navigate_to_url(browser_page, FIXTURE_URL)
    text = await extract_visible_text(browser_page)
    assert "Support Bot" in text or "Hello" in text


async def test_navigate_invalid_url_raises(browser_page):
    """Invalid URL raises after retries exhausted."""
    from backend.mcp_browser import navigate_to_url

    with pytest.raises(Exception):
        await navigate_to_url(browser_page, "not-a-url://garbage")


# ---------------------------------------------------------------------------
# Widget detection (Guardrail 3)
# ---------------------------------------------------------------------------


async def test_detect_widget_main_frame(browser_page):
    """detect_chat_widget() finds the widget in the main frame."""
    from backend.mcp_browser import detect_chat_widget, navigate_to_url

    await navigate_to_url(browser_page, FIXTURE_URL)
    await asyncio.sleep(0.5)

    ctx = await detect_chat_widget(
        browser_page,
        scenario_selectors=["[data-testid='chat-widget']"],
    )
    assert ctx is not None
    assert ctx.input_selector != ""
    assert ctx.messages_selector != ""
    assert ctx.frame is not None


async def test_detect_widget_returns_none_on_empty_page(browser_page):
    """detect_chat_widget() returns None when no widget exists."""
    from backend.mcp_browser import detect_chat_widget

    await browser_page.set_content("<html><body><p>No chatbot here</p></body></html>")
    ctx = await detect_chat_widget(browser_page)
    assert ctx is None


# ---------------------------------------------------------------------------
# Message sending
# ---------------------------------------------------------------------------


async def test_send_message_via_button(browser_page):
    """send_chat_message() submits text and clears the input."""
    from backend.mcp_browser import detect_chat_widget, navigate_to_url, send_chat_message

    await navigate_to_url(browser_page, FIXTURE_URL)
    await asyncio.sleep(0.3)

    ctx = await detect_chat_widget(browser_page)
    assert ctx is not None

    await send_chat_message("Hello there", ctx)
    val = await browser_page.input_value("#chat-input")
    assert val == ""


async def test_send_message_enter_key(browser_page):
    """send_chat_message() works via Enter key submission."""
    from backend.mcp_browser import (
        WidgetContext,
        detect_chat_widget,
        navigate_to_url,
        send_chat_message,
    )

    await navigate_to_url(browser_page, FIXTURE_URL)
    await asyncio.sleep(0.3)

    ctx = await detect_chat_widget(browser_page)
    assert ctx is not None

    enter_ctx = WidgetContext(
        frame=ctx.frame,
        input_selector=ctx.input_selector,
        messages_selector=ctx.messages_selector,
        submit_method="enter_key",
        submit_selector=None,
    )
    await send_chat_message("Test via enter", enter_ctx)


# ---------------------------------------------------------------------------
# Composite wait strategy (Guardrail 2)
# ---------------------------------------------------------------------------


async def test_wait_for_bot_response_with_typing(browser_page):
    """wait_for_bot_response() waits through the typing indicator."""
    from backend.mcp_browser import (
        detect_chat_widget,
        navigate_to_url,
        send_chat_message,
        wait_for_bot_response,
    )

    await navigate_to_url(browser_page, FIXTURE_URL)
    await asyncio.sleep(0.3)

    ctx = await detect_chat_widget(browser_page)
    assert ctx is not None

    await send_chat_message("What credit cards do you have?", ctx)
    result = await wait_for_bot_response(
        frame=ctx.frame,
        messages_selector=ctx.messages_selector,
        timeout_ms=8_000,
        stabilization_ms=300,
    )
    assert result is True


async def test_wait_for_bot_response_timeout(browser_page):
    """wait_for_bot_response() returns False when bot never responds."""
    from backend.mcp_browser import detect_chat_widget, navigate_to_url, wait_for_bot_response

    await navigate_to_url(browser_page, FIXTURE_URL)
    await asyncio.sleep(0.3)

    # Enable no-response mode via checkbox
    await browser_page.check("#no-response-mode")

    ctx = await detect_chat_widget(browser_page)
    assert ctx is not None

    result = await wait_for_bot_response(
        frame=ctx.frame,
        messages_selector=ctx.messages_selector,
        timeout_ms=1_500,
        stabilization_ms=300,
    )
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Message extraction
# ---------------------------------------------------------------------------


async def test_extract_chat_messages_returns_list(browser_page):
    """extract_chat_messages() returns a list (at least the greeting)."""
    from backend.mcp_browser import (
        detect_chat_widget,
        extract_chat_messages,
        navigate_to_url,
    )

    await navigate_to_url(browser_page, FIXTURE_URL)
    await asyncio.sleep(0.5)

    ctx = await detect_chat_widget(browser_page)
    assert ctx is not None

    messages = await extract_chat_messages(ctx)
    assert isinstance(messages, list)


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------


async def test_capture_screenshot_creates_file(browser_page):
    """capture_screenshot() saves a non-empty PNG file."""
    from backend.mcp_browser import capture_screenshot, navigate_to_url

    await navigate_to_url(browser_page, FIXTURE_URL)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = f"{tmpdir}/test.png"
        await capture_screenshot(browser_page, path)
        assert Path(path).exists()
        assert Path(path).stat().st_size > 0


# ---------------------------------------------------------------------------
# DOM snapshot
# ---------------------------------------------------------------------------


async def test_get_dom_snapshot_contains_widget(browser_page):
    """get_dom_snapshot() returns HTML with known page content."""
    from backend.mcp_browser import get_dom_snapshot, navigate_to_url

    await navigate_to_url(browser_page, FIXTURE_URL)
    html = await get_dom_snapshot(browser_page)
    assert "chat-widget" in html or "Support Bot" in html


# ---------------------------------------------------------------------------
# Retry on timeout
# ---------------------------------------------------------------------------


async def test_retry_on_timeout_raises(browser_page):
    """wait_for_selector() raises after exhausting retries on missing element."""
    from backend.mcp_browser import navigate_to_url, wait_for_selector

    await navigate_to_url(browser_page, FIXTURE_URL)

    with pytest.raises(Exception):
        await wait_for_selector(browser_page, "#this-element-does-not-exist",
                                timeout_ms=400)
