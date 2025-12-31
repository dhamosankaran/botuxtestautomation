"""FastAPI application for Citi Bot QA Platform."""
import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from pydantic import BaseModel
from dotenv import load_dotenv


load_dotenv()

from database import create_db_and_tables, get_session
from models import (
    TestRun, ConversationLog,
    StartTestRequest, StartTestResponse,
    TestResultsResponse, Metrics, HealthResponse,
    UtteranceLibraryResponse, UtteranceCategory,
    Credentials
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


# ============================================================================
# JOURNEY-BASED TESTING ENDPOINTS
# ============================================================================

from journey_engine import get_available_journeys, JourneyResult
from dataclasses import asdict


class JourneyTestRequest(BaseModel):
    """Request to start a journey test."""
    journey_name: str
    target_url: str = "https://www.citi.com"
    credentials: Optional[Credentials] = None


class JourneyInfo(BaseModel):
    """Journey information."""
    name: str
    display_name: str
    utterance_count: int
    expected_intent: str
    is_card_journey: bool
    group: str


class JourneyListResponse(BaseModel):
    """Response with list of available journeys."""
    journeys: List[JourneyInfo]
    total: int
    card_journeys: int


@app.get("/api/journey/list", response_model=JourneyListResponse)
def api_list_journeys():
    """
    Get all available journeys for testing.
    
    Returns journeys grouped by type (Cards, Account, Security, etc.)
    """
    journeys = get_available_journeys()
    
    journey_list = [
        JourneyInfo(**j) for j in journeys.values()
    ]
    
    # Sort: card journeys first, then by name
    journey_list.sort(key=lambda j: (not j.is_card_journey, j.name))
    
    card_count = sum(1 for j in journey_list if j.is_card_journey)
    
    return JourneyListResponse(
        journeys=journey_list,
        total=len(journey_list),
        card_journeys=card_count
    )


@app.post("/api/journey/start")
def api_start_journey_test(
    request: JourneyTestRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    """
    Start a journey-based test.
    
    Each utterance in the journey runs as a complete multi-turn conversation
    before the next utterance begins.
    """
    from models import Credentials
    
    # Validate journey exists
    journeys = get_available_journeys()
    if request.journey_name not in journeys:
        raise HTTPException(
            status_code=404, 
            detail=f"Journey '{request.journey_name}' not found"
        )
    
    journey_info = journeys[request.journey_name]
    
    # Create test run record
    test_run = TestRun(
        target_url=request.target_url,
        started_at=datetime.utcnow(),
        status="running",
        total_utterances=journey_info["utterance_count"]
    )
    session.add(test_run)
    session.commit()
    session.refresh(test_run)
    
    # Start journey test in background
    background_tasks.add_task(
        run_journey_test_background,
        test_run_id=test_run.id,
        journey_name=request.journey_name,
        target_url=request.target_url,
        credentials=request.credentials
    )
    
    return {
        "test_run_id": test_run.id,
        "journey_name": request.journey_name,
        "utterance_count": journey_info["utterance_count"],
        "status": "started"
    }


def run_journey_test_background(
    test_run_id: int,
    journey_name: str,
    target_url: str,
    credentials = None
):
    """
    Background task to run journey test.
    
    Reuses existing login/chat setup from engine.py
    """
    from playwright.sync_api import sync_playwright
    from engine import (
        perform_citi_login, 
        wait_for_manual_login,
        wait_for_dashboard_and_open_chat,
        PLAYWRIGHT_HEADLESS,
        PLAYWRIGHT_SLOW_MO,
        PLAYWRIGHT_TIMEOUT
    )
    from journey_engine import JourneyEngine
    from models import get_local_now
    import os
    
    CITI_USER_ID = os.getenv("CITI_USER_ID", "")
    CITI_PASSWORD = os.getenv("CITI_PASSWORD", "")
    
    print(f"[Journey Test] Starting journey '{journey_name}' (run_id={test_run_id})")
    
    context = None
    
    try:
        with sync_playwright() as p:
            user_data_dir = "/tmp/citi_browser_profile"
            
            print("Launching Chrome browser...")
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                channel="chrome",
                headless=PLAYWRIGHT_HEADLESS,
                slow_mo=PLAYWRIGHT_SLOW_MO,
                viewport={"width": 1680, "height": 1050},
                locale="en-US",
                timezone_id="America/Chicago",
                color_scheme="light",
                args=['--disable-blink-features=AutomationControlled']
            )
            
            page = context.pages[0] if context.pages else context.new_page()
            
            # Navigate and login
            print(f"Navigating to {target_url}")
            page.goto(target_url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT)
            page.wait_for_timeout(3000)
            
            # Handle login
            login_creds = credentials
            if not login_creds or not login_creds.username:
                if CITI_USER_ID and CITI_PASSWORD:
                    from models import Credentials
                    login_creds = Credentials(username=CITI_USER_ID, password=CITI_PASSWORD)
            
            if login_creds and login_creds.username:
                perform_citi_login(page, login_creds)
            else:
                print("Waiting for manual login...")
                wait_for_manual_login(page)
            
            # Open chat widget
            wait_for_dashboard_and_open_chat(page)
            
            # Run the journey
            engine = JourneyEngine(page, journey_name, test_run_id)
            result = engine.run_journey()
            
            # Update test run with final stats
            with Session(db_engine) as session:
                test_run = session.get(TestRun, test_run_id)
                if test_run:
                    test_run.status = "completed"
                    test_run.completed_at = get_local_now()
                    test_run.self_service_rate = result.overall_pass_rate
                    session.add(test_run)
                    session.commit()
            
            print(f"[Journey Test] Completed: {result.passed}/{result.total_utterances} passed")
            context.close()
            
    except Exception as e:
        print(f"[Journey Test] Failed with error: {e}")
        with Session(db_engine) as session:
            test_run = session.get(TestRun, test_run_id)
            if test_run:
                test_run.status = "failed"
                test_run.completed_at = get_local_now()
                test_run.error_message = str(e)
                session.add(test_run)
                session.commit()
        
        if context:
            try:
                context.close()
            except:
                pass
        raise


# ============================================================================
# INTELLIGENT TESTING ENDPOINTS
# ============================================================================

from intelligent_testing import (
    generate_follow_up_questions,
    generate_question_variations,
    get_edge_case_questions,
    get_custom_test_suite,
    EDGE_CASE_PATTERNS,
    EXPLORATION_SEEDS
)
from pydantic import BaseModel


class GenerateQuestionsRequest(BaseModel):
    """Request to generate follow-up questions."""
    bot_response: str
    original_question: str
    category: str = "general"
    count: int = 5


class GeneratedQuestionsResponse(BaseModel):
    """Response with generated questions."""
    questions: List[str]
    source: str
    context: str


class EdgeCasesResponse(BaseModel):
    """Response with edge case categories and questions."""
    categories: List[str]
    questions: List[dict]
    total_count: int


class CustomTestSuiteRequest(BaseModel):
    """Request to build a custom test suite."""
    include_edge_cases: bool = True
    include_exploratory: bool = True
    edge_case_categories: Optional[List[str]] = None
    generate_variations_for: Optional[List[str]] = None


class CustomTestSuiteResponse(BaseModel):
    """Response with custom test suite."""
    questions: List[dict]
    total_count: int
    categories_included: List[str]


@app.post("/api/intelligent/generate-questions", response_model=GeneratedQuestionsResponse)
def api_generate_questions(request: GenerateQuestionsRequest):
    """
    Generate dynamic follow-up questions based on bot response.
    
    Uses LLM to create natural, context-aware questions.
    """
    questions = generate_follow_up_questions(
        bot_response=request.bot_response,
        original_question=request.original_question,
        category=request.category,
        count=request.count
    )
    
    return GeneratedQuestionsResponse(
        questions=[q.question for q in questions],
        source="dynamic",
        context=request.original_question
    )


@app.post("/api/intelligent/generate-variations")
def api_generate_variations(original_question: str, count: int = 5):
    """
    Generate variations of a question to test bot understanding.
    """
    variations = generate_question_variations(original_question, count)
    
    return {
        "original": original_question,
        "variations": [v.question for v in variations],
        "count": len(variations)
    }


@app.get("/api/intelligent/edge-cases", response_model=EdgeCasesResponse)
def api_get_edge_cases(categories: Optional[str] = None):
    """
    Get pre-defined edge case questions for testing.
    
    Categories: typos, slang_informal, emoji, long_input, special_chars, 
                multilingual, minimal, questions, commands
    """
    cat_list = categories.split(",") if categories else None
    questions = get_edge_case_questions(cat_list)
    
    return EdgeCasesResponse(
        categories=list(EDGE_CASE_PATTERNS.keys()),
        questions=[
            {
                "question": q.question,
                "category": q.category,
                "source": q.source
            }
            for q in questions
        ],
        total_count=len(questions)
    )


@app.post("/api/intelligent/custom-suite", response_model=CustomTestSuiteResponse)
def api_build_custom_suite(request: CustomTestSuiteRequest):
    """
    Build a comprehensive custom test suite.
    
    Combines edge cases, exploratory questions, and optionally 
    generates variations for specific questions.
    """
    suite = get_custom_test_suite(
        include_edge_cases=request.include_edge_cases,
        include_exploratory=request.include_exploratory,
        edge_case_categories=request.edge_case_categories
    )
    
    # Generate variations if requested
    if request.generate_variations_for:
        for original in request.generate_variations_for:
            variations = generate_question_variations(original, count=3)
            suite.extend(variations)
    
    # Determine categories included
    categories_included = set()
    if request.include_edge_cases:
        if request.edge_case_categories:
            categories_included.update(request.edge_case_categories)
        else:
            categories_included.update(EDGE_CASE_PATTERNS.keys())
    if request.include_exploratory:
        categories_included.add("exploratory")
    if request.generate_variations_for:
        categories_included.add("variations")
    
    return CustomTestSuiteResponse(
        questions=[
            {
                "question": q.question,
                "category": q.category,
                "source": q.source,
                "context": q.context
            }
            for q in suite
        ],
        total_count=len(suite),
        categories_included=list(categories_included)
    )


@app.get("/api/intelligent/exploration-seeds")
def api_get_exploration_seeds():
    """
    Get seed questions for flow discovery.
    """
    return {
        "seeds": EXPLORATION_SEEDS,
        "count": len(EXPLORATION_SEEDS),
        "description": "Starting questions for discovering bot capabilities"
    }


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

from analytics import (
    get_daily_metrics,
    analyze_trends,
    get_category_breakdown,
    get_quality_stats
)


@app.get("/api/analytics/daily")
def api_get_daily_metrics(
    days: int = 7,
    session: Session = Depends(get_session)
):
    """
    Get daily aggregated metrics for the last N days.
    """
    metrics = get_daily_metrics(session, days)
    return {
        "period_days": days,
        "metrics": [m.__dict__ for m in metrics]
    }


@app.get("/api/analytics/trends")
def api_get_trends(
    period_days: int = 7,
    session: Session = Depends(get_session)
):
    """
    Get trend analysis comparing current period to previous period.
    """
    trends = analyze_trends(session, period_days)
    return trends.__dict__


@app.get("/api/analytics/categories")
def api_get_category_breakdown(
    days: int = 30,
    session: Session = Depends(get_session)
):
    """
    Get performance breakdown by category.
    """
    breakdown = get_category_breakdown(session, days)
    return {
        "period_days": days,
        "categories": [b.__dict__ for b in breakdown]
    }


@app.get("/api/analytics/quality")
def api_get_quality_stats(session: Session = Depends(get_session)):
    """
    Get comprehensive quality statistics.
    """
    return get_quality_stats(session)


# ============================================================================
# REPORT ENDPOINTS
# ============================================================================

from report_generator import (
    generate_csv_report,
    generate_markdown_report,
    get_report_summary
)
from fastapi.responses import PlainTextResponse, Response


@app.get("/api/reports/csv/{test_run_id}")
def api_export_csv(test_run_id: int, session: Session = Depends(get_session)):
    """
    Export test results as CSV.
    """
    try:
        csv_content = generate_csv_report(session, test_run_id)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=test_run_{test_run_id}.csv"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/reports/markdown/{test_run_id}")
def api_export_markdown(test_run_id: int, session: Session = Depends(get_session)):
    """
    Export test results as Markdown report.
    """
    try:
        md_content = generate_markdown_report(session, test_run_id)
        return PlainTextResponse(
            content=md_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename=test_run_{test_run_id}_report.md"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/reports/summary/{test_run_id}")
def api_get_report_summary(test_run_id: int, session: Session = Depends(get_session)):
    """
    Get a quick summary for a test run.
    """
    return get_report_summary(session, test_run_id)


# ============================================================================
# SCREENSHOT ENDPOINTS
# ============================================================================

from engine import get_screenshots_for_run
from fastapi.responses import FileResponse


@app.get("/api/screenshots/{test_run_id}")
def api_get_screenshots(test_run_id: int):
    """
    Get list of screenshots for a test run.
    """
    screenshots = get_screenshots_for_run(test_run_id)
    return {
        "test_run_id": test_run_id,
        "screenshots": screenshots,
        "count": len(screenshots)
    }


@app.get("/api/screenshots/{test_run_id}/{filename}")
def api_get_screenshot_file(test_run_id: int, filename: str):
    """
    Get a specific screenshot file.
    """
    import os
    filepath = os.path.join("screenshots", f"run_{test_run_id}", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(filepath, media_type="image/png")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
