"""
Intelligent Testing Module

Combines three key testing capabilities:
1. Dynamic Utterance Generation - LLM generates context-aware follow-up questions
2. Conversation Flow Discovery - Automatically explore all bot conversation paths
3. Custom Prompt Testing - Test with edge cases, adversarial inputs, variations

Author: Bot UX Test Automation
"""

import os
import json
import time
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from datetime import datetime

import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))  # Higher for creativity
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class GeneratedQuestion:
    """A dynamically generated test question."""
    question: str
    category: str
    source: str  # "dynamic", "edge_case", "variation", "exploratory"
    context: str  # What triggered this generation
    parent_response: str  # Bot response that led to this


@dataclass
class DiscoveredPath:
    """A discovered conversation flow path."""
    steps: List[str]  # List of user inputs/clicks
    responses: List[str]  # Bot responses at each step
    end_state: str  # Final state description
    depth: int
    discovered_at: datetime = field(default_factory=datetime.now)


@dataclass
class FlowMap:
    """Complete map of discovered bot capabilities."""
    root_question: str
    paths: List[DiscoveredPath]
    total_intents_discovered: int
    exploration_time_seconds: float
    coverage_estimate: float  # 0-100%


# ============================================================================
# EDGE CASES AND CUSTOM PROMPTS
# ============================================================================

EDGE_CASE_PATTERNS = {
    "typos": [
        "Waht is my blance?",
        "transfre money",
        "shwo my transctions",
        "pya my bill",
        "cehck my acconut",
    ],
    "slang_informal": [
        "balance plz",
        "show me da money",
        "gimme my balance",
        "yo where my money at",
        "need cash info asap",
    ],
    "emoji": [
        "💳 balance?",
        "pay 💰 bill",
        "🔒 lock card",
        "📊 transactions",
        "💸 transfer",
    ],
    "long_input": [
        "I would like to know what my current account balance is because I need to make sure I have enough money to pay my bills and also I want to transfer some money to my savings account and also check my recent transactions",
    ],
    "special_chars": [
        "what's my balance?",  # curly apostrophe
        "balance — checking",  # em dash
        "show balance (credit card)",
        "balance: checking & savings",
    ],
    "multilingual": [
        "¿Cuál es mi saldo?",  # Spanish
        "Quel est mon solde?",  # French
        "余额是多少?",  # Chinese
        "balance por favor",  # Spanglish
    ],
    "minimal": [
        "balance",
        "pay",
        "transfer",
        "card",
        "help",
        "hi",
    ],
    "questions": [
        "Can you help me?",
        "What can you do?",
        "How do I check my balance?",
        "Is there a way to see my transactions?",
    ],
    "commands": [
        "Show me my balance now",
        "Tell me my credit card balance",
        "Give me my account summary",
        "List my recent transactions",
    ],
}

# Topics to explore for flow discovery
EXPLORATION_SEEDS = [
    "What can you help me with?",
    "Show me my accounts",
    "I need help with payments",
    "Tell me about my cards",
    "Help me with transfers",
    "I have a problem",
    "How do I dispute a charge?",
    "Lock my card",
    "What's my credit limit?",
    "Show my statements",
]


# ============================================================================
# PROMPT TEMPLATES
# ============================================================================

DYNAMIC_GENERATION_PROMPT = """You are helping test a banking chatbot. Based on the bot's response, generate natural follow-up questions a real customer might ask.

## Bot's Response
{bot_response}

## Context
User originally asked: "{original_question}"
Category: {category}

## Instructions
Generate 5 different follow-up questions that:
1. Are natural and conversational
2. Test different aspects of the bot's capabilities
3. Include variations in phrasing (formal, casual, brief)
4. May probe edge cases or unclear areas
5. Follow logically from the bot's response

Return ONLY a JSON array of questions:
["question1", "question2", "question3", "question4", "question5"]
"""

FLOW_EXPLORATION_PROMPT = """You are exploring a banking chatbot to discover all its capabilities.

## Current Bot Response
{bot_response}

## Available Menu Options (if any)
{menu_options}

## Already Explored Paths
{explored_paths}

## Instructions
Analyze the response and decide the best next action to discover more capabilities:

1. If there are menu options, choose one that hasn't been explored
2. If there's a new topic mentioned, ask about it
3. If this seems like a dead end, suggest going back

Return JSON:
{{
    "action": "CLICK" | "ASK" | "BACK" | "DONE",
    "target": "menu option text or question to ask",
    "reason": "why this expands our coverage",
    "discovered_intent": "what capability we just discovered (or null)"
}}
"""

VARIATION_GENERATION_PROMPT = """Generate variations of a banking question to test the bot's understanding.

## Original Question
{original_question}

## Generate 5 Variations
Include:
1. More formal phrasing
2. More casual/brief phrasing
3. Different word order
4. With typo/misspelling
5. With additional context

Return ONLY a JSON array:
["variation1", "variation2", "variation3", "variation4", "variation5"]
"""


# ============================================================================
# CORE FUNCTIONS
# ============================================================================

def generate_follow_up_questions(
    bot_response: str,
    original_question: str,
    category: str = "general",
    count: int = 5
) -> List[GeneratedQuestion]:
    """
    Generate contextual follow-up questions based on bot response.
    
    Args:
        bot_response: The bot's latest response
        original_question: What the user originally asked
        category: Question category for context
        count: Number of questions to generate
    
    Returns:
        List of GeneratedQuestion objects
    """
    if not GEMINI_API_KEY:
        print("Warning: No API key, returning empty list")
        return []
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        prompt = DYNAMIC_GENERATION_PROMPT.format(
            bot_response=bot_response[:500],  # Truncate for prompt length
            original_question=original_question,
            category=category
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                max_output_tokens=LLM_MAX_TOKENS,
            )
        )
        
        # Parse JSON response
        text = response.text.strip()
        
        # Handle markdown code blocks
        if text.startswith("```"):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1])
        
        questions_list = json.loads(text)
        
        return [
            GeneratedQuestion(
                question=q,
                category=category,
                source="dynamic",
                context=original_question,
                parent_response=bot_response[:200]
            )
            for q in questions_list[:count]
        ]
        
    except Exception as e:
        print(f"Error generating questions: {e}")
        return []


def generate_question_variations(
    original_question: str,
    count: int = 5
) -> List[GeneratedQuestion]:
    """
    Generate variations of a question to test bot understanding.
    
    Args:
        original_question: The base question
        count: Number of variations to generate
    
    Returns:
        List of GeneratedQuestion objects
    """
    if not GEMINI_API_KEY:
        return []
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        prompt = VARIATION_GENERATION_PROMPT.format(
            original_question=original_question
        )
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.8,  # Higher for more variety
                max_output_tokens=LLM_MAX_TOKENS,
            )
        )
        
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1])
        
        variations = json.loads(text)
        
        return [
            GeneratedQuestion(
                question=v,
                category="variation",
                source="variation",
                context=original_question,
                parent_response=""
            )
            for v in variations[:count]
        ]
        
    except Exception as e:
        print(f"Error generating variations: {e}")
        return []


def get_edge_case_questions(
    categories: List[str] = None
) -> List[GeneratedQuestion]:
    """
    Get pre-defined edge case questions for testing.
    
    Args:
        categories: Which edge case categories to include (None = all)
    
    Returns:
        List of GeneratedQuestion objects
    """
    if categories is None:
        categories = list(EDGE_CASE_PATTERNS.keys())
    
    questions = []
    for category in categories:
        if category in EDGE_CASE_PATTERNS:
            for q in EDGE_CASE_PATTERNS[category]:
                questions.append(GeneratedQuestion(
                    question=q,
                    category=category,
                    source="edge_case",
                    context=f"Edge case: {category}",
                    parent_response=""
                ))
    
    return questions


def get_custom_test_suite(
    include_edge_cases: bool = True,
    include_exploratory: bool = True,
    edge_case_categories: List[str] = None
) -> List[GeneratedQuestion]:
    """
    Build a comprehensive custom test suite.
    
    Args:
        include_edge_cases: Include pre-defined edge cases
        include_exploratory: Include exploration seed questions
        edge_case_categories: Specific edge case categories
    
    Returns:
        List of GeneratedQuestion objects
    """
    suite = []
    
    if include_edge_cases:
        suite.extend(get_edge_case_questions(edge_case_categories))
    
    if include_exploratory:
        for seed in EXPLORATION_SEEDS:
            suite.append(GeneratedQuestion(
                question=seed,
                category="exploratory",
                source="exploratory",
                context="Flow discovery seed",
                parent_response=""
            ))
    
    # Shuffle for randomized testing
    random.shuffle(suite)
    
    return suite


# ============================================================================
# FLOW DISCOVERY
# ============================================================================

class FlowDiscoveryAgent:
    """
    Agent that explores all possible conversation paths in a chatbot.
    
    Usage:
        agent = FlowDiscoveryAgent()
        flow_map = agent.explore(page, max_depth=5)
    """
    
    def __init__(self, max_depth: int = 5, max_paths: int = 50):
        self.max_depth = max_depth
        self.max_paths = max_paths
        self.discovered_paths: List[DiscoveredPath] = []
        self.visited_states: Set[str] = set()
        self.discovered_intents: Set[str] = set()
    
    def explore(
        self,
        send_message_func,
        get_menu_func,
        click_menu_func,
        start_questions: List[str] = None
    ) -> FlowMap:
        """
        Explore all conversation paths.
        
        Args:
            send_message_func: Function to send message and get response
            get_menu_func: Function to extract menu options
            click_menu_func: Function to click a menu option
            start_questions: Initial questions to explore from
        
        Returns:
            FlowMap with all discovered paths
        """
        start_time = time.time()
        
        if start_questions is None:
            start_questions = EXPLORATION_SEEDS.copy()
        
        for seed in start_questions:
            if len(self.discovered_paths) >= self.max_paths:
                break
            
            try:
                self._explore_path(
                    send_message_func,
                    get_menu_func,
                    click_menu_func,
                    seed,
                    current_path=[],
                    current_responses=[],
                    depth=0
                )
            except Exception as e:
                print(f"Error exploring from '{seed}': {e}")
        
        exploration_time = time.time() - start_time
        
        return FlowMap(
            root_question="Multiple seeds",
            paths=self.discovered_paths,
            total_intents_discovered=len(self.discovered_intents),
            exploration_time_seconds=exploration_time,
            coverage_estimate=min(100, len(self.discovered_intents) * 10)
        )
    
    def _explore_path(
        self,
        send_message_func,
        get_menu_func,
        click_menu_func,
        current_input: str,
        current_path: List[str],
        current_responses: List[str],
        depth: int
    ):
        """Recursively explore a conversation path."""
        if depth >= self.max_depth:
            return
        
        if len(self.discovered_paths) >= self.max_paths:
            return
        
        # Create state signature to avoid revisiting
        state_sig = f"{current_input}|{len(current_path)}"
        if state_sig in self.visited_states:
            return
        self.visited_states.add(state_sig)
        
        # Send message and get response
        try:
            response = send_message_func(current_input)
            if not response:
                return
        except Exception as e:
            print(f"Error sending message: {e}")
            return
        
        # Update path
        new_path = current_path + [current_input]
        new_responses = current_responses + [response[:200]]
        
        # Get menu options
        menu_options = get_menu_func() if get_menu_func else []
        
        # Determine end state and discovered intent
        end_state = self._analyze_end_state(response, menu_options)
        
        # Record this path
        self.discovered_paths.append(DiscoveredPath(
            steps=new_path,
            responses=new_responses,
            end_state=end_state,
            depth=depth + 1
        ))
        
        # Extract and record intent
        intent = self._extract_intent(response, current_input)
        if intent:
            self.discovered_intents.add(intent)
        
        # Explore menu options
        if menu_options:
            for option in menu_options[:3]:  # Limit branching
                try:
                    click_menu_func(option)
                    time.sleep(1)  # Wait for response
                    
                    # Recursively explore from this option
                    self._explore_path(
                        send_message_func,
                        get_menu_func,
                        click_menu_func,
                        f"[CLICK: {option}]",
                        new_path,
                        new_responses,
                        depth + 1
                    )
                except Exception as e:
                    print(f"Error clicking '{option}': {e}")
        
        # Generate and explore follow-up questions
        if depth < self.max_depth - 1:
            follow_ups = generate_follow_up_questions(response, current_input, count=2)
            for fu in follow_ups[:1]:  # Limit branching
                self._explore_path(
                    send_message_func,
                    get_menu_func,
                    click_menu_func,
                    fu.question,
                    new_path,
                    new_responses,
                    depth + 1
                )
    
    def _analyze_end_state(self, response: str, menu_options: List[str]) -> str:
        """Determine the end state of a conversation path."""
        response_lower = response.lower()
        
        if any(kw in response_lower for kw in ["balance", "available", "$"]):
            return "Shows balance information"
        elif any(kw in response_lower for kw in ["payment", "pay", "amount due"]):
            return "Payment flow"
        elif any(kw in response_lower for kw in ["transfer", "move money"]):
            return "Transfer flow"
        elif any(kw in response_lower for kw in ["card", "lock", "replace"]):
            return "Card management"
        elif any(kw in response_lower for kw in ["transaction", "activity", "history"]):
            return "Transaction history"
        elif menu_options:
            return f"Menu with {len(menu_options)} options"
        else:
            return "Information response"
    
    def _extract_intent(self, response: str, question: str) -> Optional[str]:
        """Extract the likely intent from a response."""
        combined = f"{question} {response}".lower()
        
        intent_keywords = {
            "balance_check": ["balance", "available", "credit limit"],
            "payment": ["payment", "pay bill", "amount due"],
            "transfer": ["transfer", "move money", "send"],
            "card_management": ["lock", "unlock", "replace card", "report lost"],
            "transactions": ["transaction", "activity", "purchase", "history"],
            "dispute": ["dispute", "fraud", "unauthorized"],
            "account_info": ["account", "summary", "statement"],
        }
        
        for intent, keywords in intent_keywords.items():
            if any(kw in combined for kw in keywords):
                return intent
        
        return None
    
    def get_summary(self) -> Dict:
        """Get a summary of discovered capabilities."""
        return {
            "total_paths": len(self.discovered_paths),
            "unique_intents": list(self.discovered_intents),
            "max_depth_reached": max((p.depth for p in self.discovered_paths), default=0),
            "paths_by_end_state": self._group_by_end_state()
        }
    
    def _group_by_end_state(self) -> Dict[str, int]:
        """Group paths by their end state."""
        groups = {}
        for path in self.discovered_paths:
            groups[path.end_state] = groups.get(path.end_state, 0) + 1
        return groups


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def run_intelligent_test(
    send_message_func,
    original_question: str,
    generate_follow_ups: bool = True,
    include_variations: bool = True,
    max_questions: int = 10
) -> List[Dict]:
    """
    Run an intelligent test starting from one question.
    
    This function:
    1. Sends the original question
    2. Generates follow-up questions based on response
    3. Optionally generates variations
    4. Returns all results
    
    Args:
        send_message_func: Function(question) -> response
        original_question: Starting question
        generate_follow_ups: Whether to generate dynamic follow-ups
        include_variations: Whether to test question variations
        max_questions: Maximum total questions to test
    
    Returns:
        List of test results
    """
    results = []
    questions_tested = 0
    
    # Test original question
    response = send_message_func(original_question)
    results.append({
        "question": original_question,
        "response": response,
        "source": "original",
        "sequence": 0
    })
    questions_tested += 1
    
    # Generate and test variations
    if include_variations and questions_tested < max_questions:
        variations = generate_question_variations(original_question, count=3)
        for var in variations:
            if questions_tested >= max_questions:
                break
            var_response = send_message_func(var.question)
            results.append({
                "question": var.question,
                "response": var_response,
                "source": "variation",
                "sequence": questions_tested
            })
            questions_tested += 1
    
    # Generate and test follow-ups
    if generate_follow_ups and questions_tested < max_questions:
        follow_ups = generate_follow_up_questions(
            response, original_question, count=5
        )
        for fu in follow_ups:
            if questions_tested >= max_questions:
                break
            fu_response = send_message_func(fu.question)
            results.append({
                "question": fu.question,
                "response": fu_response,
                "source": "dynamic",
                "sequence": questions_tested
            })
            questions_tested += 1
    
    return results


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("Testing Intelligent Testing Module...")
    
    # Test edge case retrieval
    edge_cases = get_edge_case_questions(["typos", "slang_informal"])
    print(f"\nEdge cases retrieved: {len(edge_cases)}")
    for ec in edge_cases[:3]:
        print(f"  - {ec.question} ({ec.category})")
    
    # Test custom suite
    suite = get_custom_test_suite(
        include_edge_cases=True,
        include_exploratory=True,
        edge_case_categories=["minimal", "emoji"]
    )
    print(f"\nCustom test suite size: {len(suite)}")
    
    # Test LLM-based generation (if API key available)
    if GEMINI_API_KEY:
        print("\nTesting dynamic generation...")
        questions = generate_follow_up_questions(
            "I can help you with checking your balance, making payments, or managing your cards.",
            "What can you do?",
            "general"
        )
        print(f"Generated {len(questions)} follow-up questions:")
        for q in questions:
            print(f"  - {q.question}")
        
        print("\nTesting variation generation...")
        variations = generate_question_variations("What is my credit card balance?")
        print(f"Generated {len(variations)} variations:")
        for v in variations:
            print(f"  - {v.question}")
    else:
        print("\nNo API key - skipping LLM tests")
    
    print("\n✓ All tests completed!")
