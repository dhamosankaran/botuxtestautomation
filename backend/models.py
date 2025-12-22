"""Database models and API schemas."""
from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field
from pydantic import BaseModel


# ============ Database Models ============

class TestRun(SQLModel, table=True):
    """Test run record."""
    id: Optional[int] = Field(default=None, primary_key=True)
    target_url: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "running"  # running, completed, failed
    total_utterances: int = 0
    avg_latency_ms: Optional[float] = None
    self_service_rate: Optional[float] = None
    error_message: Optional[str] = None
    # NEW: LLM evaluation averages
    avg_quality_score: Optional[float] = None
    avg_relevance_score: Optional[float] = None
    avg_helpfulness_score: Optional[float] = None


class ConversationLog(SQLModel, table=True):
    """Individual conversation log entry."""
    id: Optional[int] = Field(default=None, primary_key=True)
    test_run_id: int = Field(foreign_key="testrun.id")
    utterance: str
    bot_response: str = ""
    latency_ms: int = 0
    status: str = "pending"  # pass, fail, error
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    category: str = ""  # utterance category
    
    # LLM Evaluation fields
    relevance_score: Optional[float] = None
    helpfulness_score: Optional[float] = None
    clarity_score: Optional[float] = None
    accuracy_score: Optional[float] = None
    overall_score: Optional[float] = None
    sentiment: Optional[str] = None
    llm_feedback: Optional[str] = None
    
    # NEW: Adaptive testing fields
    turns: int = 1                      # Number of conversation turns
    menu_clicks: str = ""               # JSON list of clicked menu options
    intent_identified: bool = False     # Did bot identify correct intent?
    flow_completed: bool = False        # Did bot complete the flow?
    action_history: str = ""            # JSON: [{"action":"CLICK_MENU","target":"Balance"}]


# ============ API Request/Response Schemas ============

class LoginSelectors(BaseModel):
    """CSS selectors for login form."""
    username: str = "#username"
    password: str = "#password"
    submit: str = "#signInBtn"


class ChatbotConfig(BaseModel):
    """CSS selectors for chatbot widget."""
    widget_selector: str = "[data-testid='chat-widget']"
    input_selector: str = "input[placeholder*='message'], textarea[placeholder*='message']"
    send_selector: str = "button[type='submit'], [data-testid='send-button']"
    response_selector: str = "[class*='bot-message'], [class*='assistant']"
    login_selectors: Optional[LoginSelectors] = None


class Credentials(BaseModel):
    """Login credentials."""
    username: str = ""
    password: str = ""


class StartTestRequest(BaseModel):
    """Request body for starting a test."""
    target_url: str = "https://www.citi.com"
    credentials: Optional[Credentials] = None
    utterances: List[str] = []
    utterance_categories: List[str] = []  # NEW: Categories to test
    chatbot_config: Optional[ChatbotConfig] = None
    use_library: bool = False  # NEW: Use built-in utterance library


class StartTestResponse(BaseModel):
    """Response after starting a test."""
    test_run_id: int
    status: str


class Metrics(BaseModel):
    """Calculated test metrics."""
    avg_latency_ms: float = 0
    self_service_rate: float = 0
    total_tests: int = 0
    passed: int = 0
    failed: int = 0  # NEW: Changed from escalated
    # LLM metrics
    avg_quality_score: float = 0
    avg_relevance_score: float = 0
    avg_helpfulness_score: float = 0
    # NEW: Adaptive testing metrics
    intent_accuracy: float = 0       # % of correct intent identification
    flow_completion_rate: float = 0  # % of completed flows
    avg_turns: float = 0             # Average conversation turns


class TestResultsResponse(BaseModel):
    """Response containing test results."""
    test_run: Optional[TestRun] = None
    conversations: List[ConversationLog] = []
    metrics: Metrics = Metrics()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    llm_available: bool = False  # NEW: Is LLM configured?


class UtteranceCategory(BaseModel):
    """Utterance category info."""
    name: str
    count: int
    description: str


class UtteranceLibraryResponse(BaseModel):
    """Response with utterance library info."""
    categories: List[UtteranceCategory]
    total_utterances: int
