"""Banking-specific utterance library for Citi Bot testing.

Utterances are organized by category based on common issues
reported in Digital and IVR channels.
"""
from typing import List, Dict

# Utterance categories with test questions
UTTERANCE_LIBRARY: Dict[str, List[str]] = {
    "account_balance": [
        "What is my checking account balance?",
        "Show me my account summary",
        "How much money do I have in savings?",
        "What's my available credit?",
        "Show my credit card balance",
        "What is my current balance?",
    ],
    
    "transactions": [
        "Show me my recent transactions",
        "I see a charge I don't recognize",
        "Why is there a pending transaction?",
        "When will my pending deposit clear?",
        "Show transactions from last week",
        "I need to dispute a charge",
    ],
    
    "payments": [
        "How do I pay my credit card bill?",
        "I want to make a payment",
        "Schedule a payment for next week",
        "Set up autopay for my credit card",
        "When is my payment due?",
        "Can I change my payment due date?",
    ],
    
    "card_issues": [
        "My card was declined",
        "I lost my debit card",
        "My card was stolen",
        "I want to report fraud on my account",
        "Replace my damaged card",
        "Why was my transaction declined?",
        "Lock my credit card",
        "Unlock my card",
    ],
    
    "transfers": [
        "Transfer money to my savings account",
        "How do I send money to someone?",
        "Set up a wire transfer",
        "Transfer between my accounts",
        "What are the transfer limits?",
        "Cancel a pending transfer",
    ],
    
    "account_management": [
        "How do I update my address?",
        "Change my phone number",
        "Update my email address",
        "How do I close my account?",
        "Add an authorized user",
        "Request a credit limit increase",
    ],
    
    "login_security": [
        "I forgot my password",
        "Reset my password",
        "My account is locked",
        "Unlock my online account",
        "How do I set up two-factor authentication?",
        "I'm having trouble logging in",
    ],
    
    "rewards_benefits": [
        "How many reward points do I have?",
        "How do I redeem my rewards?",
        "Check my cashback balance",
        "What benefits does my card have?",
        "How do I earn more points?",
    ],
    
    "statements_documents": [
        "View my statements",
        "Download my statement",
        "I need a copy of my tax form",
        "Where can I find my 1099?",
        "Get my account documents",
    ],
    
    "escalation_test": [
        "I need to speak to a human",
        "Connect me to an agent",
        "Transfer me to customer service",
        "I want to talk to a real person",
        "This isn't helping, get me a representative",
    ],
    
    "loans_offers": [
        "What loan options do I have?",
        "Check if I'm pre-approved for anything",
        "Tell me about personal loans",
        "What's my interest rate?",
        "How do I apply for a loan?",
    ],
    
    "fees_charges": [
        "Why was I charged a fee?",
        "How do I avoid monthly fees?",
        "Waive my late payment fee",
        "What are the ATM fees?",
        "Explain this fee on my statement",
    ],
    
    "credit_card": [
        "Show my credit card balance",
        "What's my available credit?",
        "When is my credit card payment due?",
        "How do I pay my credit card bill?",
        "Set up autopay for my credit card",
        "Lock my credit card",
        "Check my rewards points",
    ],
}

# Expected intents for LLM evaluation context
EXPECTED_INTENTS = {
    "account_balance": "The bot should provide account balance information or guide user to view balances",
    "transactions": "The bot should show transactions or help with transaction inquiries/disputes",
    "payments": "The bot should help set up, schedule, or manage payments",
    "card_issues": "The bot should help with card replacement, locking, or fraud reporting",
    "transfers": "The bot should assist with money transfers between accounts or to others",
    "account_management": "The bot should help update account information or settings",
    "login_security": "The bot should help with password reset, account unlock, or security settings",
    "rewards_benefits": "The bot should provide rewards balance or redemption information",
    "statements_documents": "The bot should help access statements or tax documents",
    "escalation_test": "The bot should transfer to a human agent when requested",
    "loans_offers": "The bot should provide loan information or pre-approval status",
    "fees_charges": "The bot should explain fees or help with fee waivers",
    "credit_card": "The bot should provide credit card balance, payment info, or help manage credit card settings",
}


def get_all_utterances() -> List[str]:
    """Get all utterances as a flat list."""
    all_utterances = []
    for category_utterances in UTTERANCE_LIBRARY.values():
        all_utterances.extend(category_utterances)
    return all_utterances


def get_utterances_by_category(category: str) -> List[str]:
    """Get utterances for a specific category."""
    return UTTERANCE_LIBRARY.get(category, [])


def get_categories() -> List[str]:
    """Get all available categories."""
    return list(UTTERANCE_LIBRARY.keys())


def get_category_for_utterance(utterance: str) -> str:
    """Find the category for a given utterance."""
    for category, utterances in UTTERANCE_LIBRARY.items():
        if utterance in utterances:
            return category
    return "unknown"


def get_expected_intent(category: str) -> str:
    """Get the expected intent description for a category."""
    return EXPECTED_INTENTS.get(category, "Unknown intent")
