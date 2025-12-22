"""FastAPI application for Citi Bot QA Platform."""
import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from dotenv import load_dotenv

load_dotenv()

from database import create_db_and_tables, get_session
from models import (
    TestRun, ConversationLog,
    StartTestRequest, StartTestResponse,
    TestResultsResponse, Metrics, HealthResponse,
    UtteranceLibraryResponse, UtteranceCategory
)
from engine import run_chatbot_test
from utterances import (
    get_all_utterances, get_categories, 
    get_utterances_by_category, EXPECTED_INTENTS,
    UTTERANCE_LIBRARY
)

app = FastAPI(
    title="Citi Bot QA Platform",
    description="Automated testing platform for Citi chatbot with LLM evaluation",
    version="2.0.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Initialize database on startup."""
    create_db_and_tables()


@app.get("/api/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    llm_available = bool(os.getenv("GEMINI_API_KEY"))
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        llm_available=llm_available
    )


@app.get("/api/utterances", response_model=UtteranceLibraryResponse)
def get_utterance_library():
    """Get the built-in utterance library."""
    categories = []
    for name, utterances in UTTERANCE_LIBRARY.items():
        categories.append(UtteranceCategory(
            name=name,
            count=len(utterances),
            description=EXPECTED_INTENTS.get(name, "")
        ))
    
    return UtteranceLibraryResponse(
        categories=categories,
        total_utterances=len(get_all_utterances())
    )


@app.get("/api/utterances/{category}", response_model=List[str])
def get_category_utterances(category: str):
    """Get utterances for a specific category."""
    utterances = get_utterances_by_category(category)
    if not utterances:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
    return utterances


@app.post("/api/start-test", response_model=StartTestResponse)
def start_test(
    request: StartTestRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Start a new chatbot test.
    
    The test runs in the background using Playwright.
    Poll /api/results to get live updates.
    """
    # Build utterance list
    utterances = list(request.utterances) if request.utterances else []
    
    # Add utterances from categories if use_library is True
    if request.use_library:
        if request.utterance_categories:
            # Add utterances from specific categories
            for cat in request.utterance_categories:
                utterances.extend(get_utterances_by_category(cat))
        else:
            # Add all utterances from library
            utterances.extend(get_all_utterances())
    
    # Validate
    if not utterances:
        raise HTTPException(status_code=400, detail="At least one utterance is required")
    
    # Default to Citi.com if no URL provided
    target_url = request.target_url or "https://www.citi.com"
    
    # Create test run record
    test_run = TestRun(
        target_url=target_url,
        started_at=datetime.utcnow(),
        status="running",
        total_utterances=len(utterances)
    )
    session.add(test_run)
    session.commit()
    session.refresh(test_run)
    
    # Start test in background
    background_tasks.add_task(
        run_chatbot_test,
        test_run_id=test_run.id,
        target_url=target_url,
        utterances=utterances,
        credentials=request.credentials,
        chatbot_config=request.chatbot_config
    )
    
    return StartTestResponse(
        test_run_id=test_run.id,
        status="started"
    )


@app.get("/api/results", response_model=TestResultsResponse)
def get_results(
    test_run_id: Optional[int] = None,
    session: Session = Depends(get_session)
):
    """
    Get test results and metrics.
    
    If test_run_id is not provided, returns the latest test run.
    """
    # Get test run
    if test_run_id:
        test_run = session.get(TestRun, test_run_id)
    else:
        # Get latest test run
        statement = select(TestRun).order_by(TestRun.id.desc()).limit(1)
        test_run = session.exec(statement).first()
    
    if not test_run:
        return TestResultsResponse()
    
    # Get conversation logs
    statement = select(ConversationLog).where(
        ConversationLog.test_run_id == test_run.id
    ).order_by(ConversationLog.id)
    conversations = session.exec(statement).all()
    
    # Calculate metrics
    total = len(conversations)
    passed = sum(1 for c in conversations if c.status == "pass")
    escalated = sum(1 for c in conversations if c.status == "escalated")
    
    latencies = [c.latency_ms for c in conversations if c.latency_ms > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    self_service_rate = ((total - escalated) / total * 100) if total > 0 else 0
    
    # LLM metrics
    quality_scores = [c.overall_score for c in conversations if c.overall_score]
    relevance_scores = [c.relevance_score for c in conversations if c.relevance_score]
    helpfulness_scores = [c.helpfulness_score for c in conversations if c.helpfulness_score]
    
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0
    avg_helpfulness = sum(helpfulness_scores) / len(helpfulness_scores) if helpfulness_scores else 0
    
    metrics = Metrics(
        avg_latency_ms=round(avg_latency, 2),
        self_service_rate=round(self_service_rate, 2),
        total_tests=total,
        passed=passed,
        escalated=escalated,
        avg_quality_score=round(avg_quality, 2),
        avg_relevance_score=round(avg_relevance, 2),
        avg_helpfulness_score=round(avg_helpfulness, 2)
    )
    
    return TestResultsResponse(
        test_run=test_run,
        conversations=list(conversations),
        metrics=metrics
    )


@app.get("/api/test-runs", response_model=List[TestRun])
def get_test_runs(
    limit: int = 10,
    session: Session = Depends(get_session)
):
    """Get list of all test runs."""
    statement = select(TestRun).order_by(TestRun.id.desc()).limit(limit)
    test_runs = session.exec(statement).all()
    return list(test_runs)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
