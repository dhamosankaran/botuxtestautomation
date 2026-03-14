"""SQLModel database schemas for BOTTestAutomation.

Three-table hierarchy: TestRun → ConversationThread → MessageExchange.
"""
import uuid
import logging
from datetime import datetime
from typing import Generator, Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

logger = logging.getLogger(__name__)

_DB_PATH = "sqlite:///./bottest.db"
_engine = None


def get_engine():
    """Return the singleton SQLite engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _DB_PATH,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def create_tables() -> None:
    """Create all database tables if they do not already exist."""
    SQLModel.metadata.create_all(get_engine())
    logger.info("Database tables created/verified at %s", _DB_PATH)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session and close it on exit."""
    with Session(get_engine()) as session:
        yield session


class TestRun(SQLModel, table=True):
    """Top-level record for a single scenario test execution."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    scenario_name: str
    target_url: str
    status: str  # PASS | FAIL | ERROR | PARTIAL
    red_team_enabled: bool = False
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_turns: int = 0
    duration_seconds: Optional[float] = None
    report_path: str  # Path to reports/[run_id]/ directory


class ConversationThread(SQLModel, table=True):
    """One conversation thread within a TestRun."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    test_run_id: str = Field(foreign_key="testrun.id")
    thread_index: int = 0  # For multi-thread scenarios
    status: str = "active"


class MessageExchange(SQLModel, table=True):
    """A single turn within a ConversationThread."""

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
    )
    thread_id: str = Field(foreign_key="conversationthread.id")
    turn_number: int
    sender: str  # "user" | "bot" | "system"
    content: str
    timestamp: datetime
    bot_response_ms: Optional[int] = None
    sentiment_score: Optional[float] = None  # -1.0 to 1.0
    security_flag: Optional[str] = None  # prompt_leak | injection_success | deflected
    agent_reasoning: Optional[str] = None  # REASON step summary


def persist_session_to_db(
    session,  # SessionState — avoid circular import
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    report_path: str,
    sentiment_by_turn: Optional[dict] = None,
) -> None:
    """Persist a completed SessionState to the SQLite database.

    Creates one TestRun, one ConversationThread, and one MessageExchange per
    history entry.  Idempotent on duplicate run_id (silently skips on error).

    Args:
        session: Completed SessionState from engine.py.
        run_id: Unique run identifier (used as TestRun primary key).
        started_at: Run start timestamp.
        completed_at: Run end timestamp.
        report_path: Absolute path to the reports/[run_id]/ directory.
        sentiment_by_turn: Optional mapping of turn_number → sentiment score.
    """
    if sentiment_by_turn is None:
        sentiment_by_turn = {}
    try:
        engine = get_engine()
        with Session(engine) as db:
            test_run = TestRun(
                id=run_id,
                scenario_name=session.scenario.get("name", "Unknown"),
                target_url=session.scenario.get("target_url", ""),
                status=session.final_status,
                red_team_enabled=bool(getattr(session, "red_team_active", False)),
                started_at=started_at,
                completed_at=completed_at,
                total_turns=session.turn,
                duration_seconds=round((completed_at - started_at).total_seconds(), 2),
                report_path=report_path,
            )
            db.add(test_run)
            db.flush()

            thread = ConversationThread(
                test_run_id=run_id,
                thread_index=0,
                status=session.final_status,
            )
            db.add(thread)
            db.flush()

            for entry in session.history:
                msg = MessageExchange(
                    thread_id=thread.id,
                    turn_number=entry.turn,
                    sender=entry.sender,
                    content=entry.content,
                    timestamp=entry.timestamp,
                    bot_response_ms=entry.bot_response_ms,
                    agent_reasoning=entry.agent_reasoning,
                    sentiment_score=sentiment_by_turn.get(entry.turn) if entry.sender == "bot" else None,
                )
                db.add(msg)

            db.commit()
            logger.info(
                "DB persisted: run_id=%s  turns=%d  messages=%d",
                run_id, session.turn, len(session.history),
            )
    except Exception as exc:
        logger.error("DB persistence failed (non-fatal): %s", exc)
