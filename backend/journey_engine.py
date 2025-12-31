"""
Journey Engine - Sequential Utterance Testing with LLM-Driven Conversations

This engine processes utterances ONE AT A TIME, running each as a complete
multi-turn conversation before moving to the next utterance.

Flow:
1. User selects a journey (e.g., "Cards Dispute")
2. Engine takes utterance #1, runs complete conversation
3. LLM decides each turn: click menu, type follow-up, or complete
4. After flow completes → record result → move to utterance #2
5. Repeat until all utterances tested
"""

import time
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field, asdict
from playwright.sync_api import Page
from sqlmodel import Session

from database import engine as db_engine
from models import TestRun, ConversationLog, get_local_now
from llm_evaluator import analyze_and_decide, AdaptiveDecision
from utterances import UTTERANCE_LIBRARY, EXPECTED_INTENTS
# Import enhanced menu functions from engine.py
from engine import (
    extract_menu_options,
    click_menu_option,
    wait_for_menu_options,
    detect_clarifying_question,
    detect_yes_no_confirmation,
    is_invalid_response
)


@dataclass
class ConversationTurn:
    """Single turn in a conversation."""
    turn_number: int
    user_message: str
    bot_response: str
    action_taken: str  # "initial", "follow_up", "click_menu", "complete"
    menu_clicked: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class UtteranceResult:
    """Result of testing a single utterance through its full conversation."""
    utterance: str
    status: str  # "pass", "fail", "error"
    total_turns: int
    conversation_history: List[ConversationTurn]
    final_score: float
    llm_reason: str
    intent_identified: bool
    flow_completed: bool
    duration_seconds: float


@dataclass
class JourneyResult:
    """Result of testing an entire journey."""
    journey_name: str
    total_utterances: int
    passed: int
    failed: int
    utterance_results: List[UtteranceResult]
    started_at: str
    completed_at: str
    overall_pass_rate: float


# Callbacks for real-time progress updates
ProgressCallback = Callable[[str, int, int, Optional[UtteranceResult]], None]


class JourneyEngine:
    """
    Engine for journey-based testing with sequential utterance processing.
    
    Each utterance runs as a complete multi-turn conversation before
    the next utterance begins.
    """
    
    MAX_TURNS_PER_UTTERANCE = 8  # Maximum conversation turns per utterance
    
    def __init__(
        self,
        page: Page,
        journey_name: str,
        test_run_id: int,
        progress_callback: Optional[ProgressCallback] = None
    ):
        """
        Initialize the journey engine.
        
        Args:
            page: Playwright page with chat widget open
            journey_name: Category/journey name (e.g., "cards_dispute")
            test_run_id: Database test run ID
            progress_callback: Optional callback for real-time updates
        """
        self.page = page
        self.journey_name = journey_name
        self.test_run_id = test_run_id
        self.progress_callback = progress_callback
        
        # Get utterances for this journey
        self.utterances = UTTERANCE_LIBRARY.get(journey_name, [])
        self.expected_intent = EXPECTED_INTENTS.get(journey_name, "")
        
        print(f"[JourneyEngine] Initialized for '{journey_name}' with {len(self.utterances)} utterances")
    
    def run_journey(self) -> JourneyResult:
        """
        Run the complete journey test.
        
        Processes each utterance sequentially, running a full conversation
        for each before moving to the next.
        
        Returns:
            JourneyResult with all utterance results
        """
        started_at = datetime.now().isoformat()
        utterance_results: List[UtteranceResult] = []
        passed = 0
        failed = 0
        
        print(f"\n{'='*60}")
        print(f"STARTING JOURNEY: {self.journey_name.upper()}")
        print(f"Total utterances to test: {len(self.utterances)}")
        print(f"{'='*60}\n")
        
        for idx, utterance in enumerate(self.utterances, 1):
            print(f"\n{'─'*50}")
            print(f"[{idx}/{len(self.utterances)}] Testing utterance:")
            print(f"   \"{utterance}\"")
            print(f"{'─'*50}")
            
            # Notify progress
            if self.progress_callback:
                self.progress_callback(
                    "testing", idx, len(self.utterances), None
                )
            
            # Run the full conversation for this utterance
            result = self._run_utterance_conversation(utterance, idx)
            utterance_results.append(result)
            
            # Track pass/fail
            if result.status == "pass":
                passed += 1
            else:
                failed += 1
            
            # Save to database
            self._save_utterance_result(result, idx)
            
            # Notify completion
            if self.progress_callback:
                self.progress_callback(
                    "completed", idx, len(self.utterances), result
                )
            
            # Brief pause between utterances to let bot reset
            if idx < len(self.utterances):
                print(f"   Waiting 2s before next utterance...")
                time.sleep(2)
        
        completed_at = datetime.now().isoformat()
        overall_pass_rate = (passed / len(self.utterances) * 100) if self.utterances else 0
        
        print(f"\n{'='*60}")
        print(f"JOURNEY COMPLETE: {self.journey_name.upper()}")
        print(f"Results: {passed} passed, {failed} failed ({overall_pass_rate:.1f}% pass rate)")
        print(f"{'='*60}\n")
        
        return JourneyResult(
            journey_name=self.journey_name,
            total_utterances=len(self.utterances),
            passed=passed,
            failed=failed,
            utterance_results=utterance_results,
            started_at=started_at,
            completed_at=completed_at,
            overall_pass_rate=round(overall_pass_rate, 1)
        )
    
    def _run_utterance_conversation(self, utterance: str, utterance_idx: int) -> UtteranceResult:
        """
        Run a complete multi-turn conversation for a single utterance.
        
        The LLM decides each turn what to do:
        - CLICK_MENU: Click a menu option
        - CONTINUE: Send a follow-up message
        - PASS: Flow completed successfully
        - FAIL: Flow failed or stuck
        
        Args:
            utterance: The initial user message
            utterance_idx: Index for logging
            
        Returns:
            UtteranceResult with full conversation history
        """
        start_time = time.time()
        conversation_history: List[ConversationTurn] = []
        current_message = utterance
        turn_number = 0
        
        final_decision = None
        
        while turn_number < self.MAX_TURNS_PER_UTTERANCE:
            turn_number += 1
            
            # Determine action type
            is_initial = (turn_number == 1)
            action_type = "initial" if is_initial else "follow_up"
            
            print(f"   Turn {turn_number}: Sending message...")
            
            # Track message count BEFORE sending (to detect new messages)
            previous_message_count = self._get_message_count()
            
            # Send the message to bot
            self._send_message_to_bot(current_message)
            
            # Wait for and capture bot response (passing previous count for delta detection)
            bot_response = self._get_bot_response(previous_count=previous_message_count)
            print(f"   Turn {turn_number}: Bot responded ({len(bot_response)} chars)")

            
            # ENHANCED: Detect if bot is asking a clarifying question
            # If so, we need to wait longer for menu options to appear
            is_clarifying = detect_clarifying_question(bot_response)
            if is_clarifying:
                print(f"   Turn {turn_number}: Detected clarifying question - waiting for menu options...")
                # Use enhanced menu detection from engine.py
                menu_options = wait_for_menu_options(self.page, timeout_ms=6000)
            else:
                # Use enhanced menu extraction from engine.py with wait
                menu_options = extract_menu_options(self.page, wait_for_options=True)
            
            if menu_options:
                print(f"   Turn {turn_number}: Found {len(menu_options)} menu options: {menu_options[:3]}")
            
            # Record this turn
            turn = ConversationTurn(
                turn_number=turn_number,
                user_message=current_message,
                bot_response=bot_response[:500],  # Truncate for storage
                action_taken=action_type
            )
            conversation_history.append(turn)
            
            # Ask LLM what to do next - pass conversation history for loop detection
            action_history_for_llm = [
                {
                    "turn": t.turn_number,
                    "action": t.action_taken,
                    "menu_choice": t.menu_clicked,
                    "reason": ""
                }
                for t in conversation_history
            ]
            decision = analyze_and_decide(
                utterance=utterance,  # Always pass original intent
                bot_response=bot_response,
                menu_options=menu_options,
                action_history=action_history_for_llm
            )
            
            print(f"   Turn {turn_number}: LLM decision = {decision.action} (score: {decision.score})")
            
            # Execute the decision
            if decision.action == "PASS":
                print(f"   ✅ Flow PASSED - {decision.reason}")
                final_decision = decision
                break
                
            elif decision.action == "FAIL":
                print(f"   ❌ Flow FAILED - {decision.reason}")
                final_decision = decision
                break
                
            elif decision.action == "CLICK_MENU" and decision.menu_choice:
                # Click the menu option - use enhanced click function from engine.py
                clicked = click_menu_option(self.page, decision.menu_choice)
                if clicked:
                    turn.action_taken = "click_menu"
                    turn.menu_clicked = decision.menu_choice
                    print(f"   Turn {turn_number}: Clicked menu: {decision.menu_choice}")
                    
                    # Wait for new bot response after clicking (click_menu_option already waits 1.5s)
                    time.sleep(1.5)  # Extra wait for response
                    menu_click_count = self._get_message_count()
                    bot_response = self._get_bot_response(previous_count=menu_click_count - 1)
                    
                    # Re-evaluate after click
                    continue
                else:
                    print(f"   Turn {turn_number}: Failed to click menu, sending follow-up instead")
                    current_message = decision.follow_up or f"I'd like help with {utterance}"
                    
            elif decision.action == "CONTINUE" and decision.follow_up:
                current_message = decision.follow_up
                print(f"   Turn {turn_number}: Will send follow-up: {current_message[:50]}...")
                
            else:
                # Unknown action, try generic follow-up
                current_message = f"Can you help me with {utterance}?"
        
        # If we exhausted turns without a final decision
        if not final_decision:
            print(f"   ⚠️ Max turns ({self.MAX_TURNS_PER_UTTERANCE}) reached")
            final_decision = AdaptiveDecision(
                action="FAIL",
                reason=f"Max turns ({self.MAX_TURNS_PER_UTTERANCE}) reached without resolution",
                score=3.0,
                intent_identified=False,
                flow_completed=False
            )
        
        duration = time.time() - start_time
        
        return UtteranceResult(
            utterance=utterance,
            status="pass" if final_decision.action == "PASS" else "fail",
            total_turns=turn_number,
            conversation_history=conversation_history,
            final_score=final_decision.score,
            llm_reason=final_decision.reason,
            intent_identified=final_decision.intent_identified,
            flow_completed=final_decision.flow_completed,
            duration_seconds=round(duration, 2)
        )
    
    def _send_message_to_bot(self, message: str):
        """Send a message to the chat bot."""
        input_selectors = [
            "textarea[placeholder*='message' i]",
            "input[placeholder*='message' i]",
            "textarea[placeholder*='write' i]",
            "[class*='input'][contenteditable='true']",
            "[class*='chat'] textarea",
            "[class*='chat'] input[type='text']",
        ]
        
        for selector in input_selectors:
            try:
                field = self.page.locator(selector).first
                if field.is_visible():
                    field.fill(message)
                    self.page.wait_for_timeout(300)
                    
                    # Try to send
                    self.page.keyboard.press("Enter")
                    self.page.wait_for_timeout(1500)
                    return
            except Exception:
                continue
        
        print(f"   Warning: Could not find chat input field")
    
    def _get_message_count(self) -> int:
        """Get current count of bot messages in chat."""
        response_selectors = [
            "[class*='message-content']",
            "[class*='chat-message']",
            "[class*='bot-message']",
            "[class*='bubble']",
        ]
        
        for selector in response_selectors:
            try:
                elements = self.page.query_selector_all(selector)
                if elements:
                    return len(elements)
            except Exception:
                continue
        return 0
    
    def _get_bot_response(self, timeout_ms: int = 15000, previous_count: int = 0) -> str:
        """
        Wait for and get the bot's NEW response.
        
        Improved logic:
        1. Wait for message count to increase (new message appeared)
        2. Wait for that message to stabilize (not still typing)
        3. Return the latest message content
        """
        response_selectors = [
            "[class*='message-content']",
            "[class*='chat-message']",
            "[class*='bot-message']",
            "[class*='assistant-message']",
            "[class*='bubble']",
            "[class*='response']",
        ]
        
        # First, wait for a NEW message to appear
        elapsed = 0
        new_message_detected = False
        
        while elapsed < timeout_ms:
            current_count = self._get_message_count()
            if current_count > previous_count:
                new_message_detected = True
                print(f"      [Response] New message detected (count: {previous_count} -> {current_count})")
                break
            
            self.page.wait_for_timeout(500)
            elapsed += 500
        
        if not new_message_detected:
            print(f"      [Response] No new message after {timeout_ms}ms, using latest available")
        
        # Now wait for the response to stabilize (2 consecutive identical reads)
        last_response = ""
        stable_count = 0
        stabilize_elapsed = 0
        max_stabilize_wait = 8000  # Max 8 seconds to stabilize
        
        while stabilize_elapsed < max_stabilize_wait:
            current_response = ""
            
            for selector in response_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    if elements:
                        # Get the LAST message (most recent)
                        latest = elements[-1]
                        text = (latest.text_content() or "").strip()
                        
                        if text and len(text) > 10:
                            # Skip typing indicators and loading states
                            lower_text = text.lower()
                            if any(skip in lower_text for skip in ["typing", "loading", "please wait", "..."]):
                                continue
                            current_response = text
                            break
                except Exception:
                    continue
            
            if current_response:
                if current_response == last_response:
                    stable_count += 1
                    if stable_count >= 3:  # Need 3 consecutive same reads (1.5 seconds stable)
                        print(f"      [Response] Stable after {stabilize_elapsed}ms ({len(current_response)} chars)")
                        return current_response
                else:
                    stable_count = 0
                    last_response = current_response
            
            self.page.wait_for_timeout(500)
            stabilize_elapsed += 500
        
        print(f"      [Response] Returning after stabilization timeout ({len(last_response)} chars)")
        return last_response or ""

    
    def _get_menu_options(self) -> List[str]:
        """Get available menu/button options from the chat."""
        menu_selectors = [
            "[class*='quick-reply'] button",
            "[class*='chip']",
            "[class*='suggestion']",
            "[class*='option'] button",
            "[class*='menu'] button",
            "button[class*='action']",
        ]
        
        options = []
        for selector in menu_selectors:
            try:
                buttons = self.page.query_selector_all(selector)
                for btn in buttons:
                    text = (btn.text_content() or "").strip()
                    if text and len(text) > 1 and len(text) < 100:
                        options.append(text)
            except Exception:
                continue
        
        return list(set(options))  # Remove duplicates
    
    def _click_menu_option(self, option_text: str) -> bool:
        """Click a menu option by its text."""
        try:
            # Try exact match first
            button = self.page.locator(f"button:has-text('{option_text}')").first
            if button.is_visible():
                button.click()
                self.page.wait_for_timeout(1000)
                return True
        except Exception:
            pass
        
        try:
            # Try partial match
            button = self.page.get_by_text(option_text, exact=False).first
            if button.is_visible():
                button.click()
                self.page.wait_for_timeout(1000)
                return True
        except Exception:
            pass
        
        return False
    
    def _save_utterance_result(self, result: UtteranceResult, index: int):
        """Save utterance result to database."""
        try:
            with Session(db_engine) as session:
                log = ConversationLog(
                    test_run_id=self.test_run_id,
                    utterance=result.utterance,
                    bot_response=result.conversation_history[-1].bot_response if result.conversation_history else "",
                    latency_ms=int(result.duration_seconds * 1000),
                    status=result.status,
                    category=self.journey_name,
                    overall_score=result.final_score,
                    llm_feedback=result.llm_reason,
                    turns=result.total_turns,
                    intent_identified=result.intent_identified,
                    flow_completed=result.flow_completed,
                    action_history=json.dumps([asdict(t) for t in result.conversation_history])
                )
                session.add(log)
                session.commit()
                print(f"   Saved result to database (ID: {log.id})")
        except Exception as e:
            print(f"   Warning: Failed to save result: {e}")


def get_available_journeys() -> Dict[str, dict]:
    """
    Get all available journeys grouped by category.
    
    Returns:
        Dict with journey info including name, utterance count, description
    """
    # Card-focused journeys (high volume)
    card_journeys = [
        "card_issues",
        "cards_dispute", 
        "cards_balance_transfer",
        "cards_replacement",
        "cards_update_contact",
        "credit_card",
    ]
    
    journeys = {}
    for name, utterances in UTTERANCE_LIBRARY.items():
        journeys[name] = {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "utterance_count": len(utterances),
            "expected_intent": EXPECTED_INTENTS.get(name, ""),
            "is_card_journey": name in card_journeys,
            "group": "Cards" if name in card_journeys else "Other"
        }
    
    return journeys


def run_journey_test(
    page: Page,
    journey_name: str,
    test_run_id: int,
    progress_callback: Optional[ProgressCallback] = None
) -> JourneyResult:
    """
    Convenience function to run a journey test.
    
    Args:
        page: Playwright page with chat widget open
        journey_name: Journey category name
        test_run_id: Database test run ID
        progress_callback: Optional progress callback
        
    Returns:
        JourneyResult with all utterance results
    """
    engine = JourneyEngine(page, journey_name, test_run_id, progress_callback)
    return engine.run_journey()
