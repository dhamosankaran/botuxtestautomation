"""Unit tests for backend/models.py — table creation, CRUD, FK relationships."""
import pytest
from datetime import datetime, timezone

from sqlmodel import Session, SQLModel, create_engine, select

from backend.models import (
    ConversationThread,
    MessageExchange,
    TestRun,
    create_tables,
)


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------


def test_tables_created_via_create_tables(tmp_path, monkeypatch):
    """create_tables() creates all three tables without errors."""
    import backend.models as m

    db_file = tmp_path / "test.db"
    monkeypatch.setattr(m, "_DB_PATH", f"sqlite:///{db_file}")
    monkeypatch.setattr(m, "_engine", None)

    m.create_tables()

    from sqlalchemy import inspect as sql_inspect

    inspector = sql_inspect(m.get_engine())
    tables = inspector.get_table_names()
    assert "testrun" in tables
    assert "conversationthread" in tables
    assert "messageexchange" in tables


# ---------------------------------------------------------------------------
# TestRun CRUD
# ---------------------------------------------------------------------------


def test_create_and_read_test_run(session: Session):
    """TestRun row is written and retrieved correctly."""
    run = TestRun(
        scenario_name="Basic Test",
        target_url="https://example.com",
        status="PASS",
        started_at=datetime.now(timezone.utc),
        report_path="reports/test/",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    fetched = session.get(TestRun, run.id)
    assert fetched is not None
    assert fetched.scenario_name == "Basic Test"
    assert fetched.status == "PASS"
    assert fetched.red_team_enabled is False
    assert fetched.total_turns == 0


def test_update_test_run_status(session: Session):
    """TestRun status can be updated after creation."""
    run = TestRun(
        scenario_name="Update Test",
        target_url="https://example.com",
        status="PARTIAL",
        started_at=datetime.now(timezone.utc),
        report_path="reports/update/",
    )
    session.add(run)
    session.commit()

    run.status = "PASS"
    run.total_turns = 5
    session.add(run)
    session.commit()
    session.refresh(run)

    assert run.status == "PASS"
    assert run.total_turns == 5


def test_delete_test_run(session: Session):
    """TestRun row is removed after deletion."""
    run = TestRun(
        scenario_name="Delete Test",
        target_url="https://example.com",
        status="FAIL",
        started_at=datetime.now(timezone.utc),
        report_path="reports/delete/",
    )
    session.add(run)
    session.commit()
    run_id = run.id

    session.delete(run)
    session.commit()

    assert session.get(TestRun, run_id) is None


def test_test_run_defaults(session: Session):
    """TestRun optional fields default to None / False / 0."""
    run = TestRun(
        scenario_name="Defaults",
        target_url="https://example.com",
        status="PASS",
        started_at=datetime.now(timezone.utc),
        report_path="reports/defaults/",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    assert run.completed_at is None
    assert run.duration_seconds is None
    assert run.red_team_enabled is False
    assert run.total_turns == 0


# ---------------------------------------------------------------------------
# ConversationThread CRUD + FK
# ---------------------------------------------------------------------------


def test_create_conversation_thread(session: Session):
    """ConversationThread references TestRun correctly."""
    run = TestRun(
        scenario_name="FK Test",
        target_url="https://example.com",
        status="PASS",
        started_at=datetime.now(timezone.utc),
        report_path="reports/fk/",
    )
    session.add(run)
    session.commit()

    thread = ConversationThread(test_run_id=run.id, thread_index=0)
    session.add(thread)
    session.commit()
    session.refresh(thread)

    assert thread.id is not None
    assert thread.test_run_id == run.id
    assert thread.status == "active"


def test_multiple_threads_per_run(session: Session):
    """Multiple ConversationThreads can belong to one TestRun."""
    run = TestRun(
        scenario_name="Multi Thread",
        target_url="https://example.com",
        status="PASS",
        started_at=datetime.now(timezone.utc),
        report_path="reports/multi/",
    )
    session.add(run)
    session.commit()

    for i in range(3):
        session.add(ConversationThread(test_run_id=run.id, thread_index=i))
    session.commit()

    threads = session.exec(
        select(ConversationThread).where(ConversationThread.test_run_id == run.id)
    ).all()
    assert len(threads) == 3


# ---------------------------------------------------------------------------
# MessageExchange CRUD + FK
# ---------------------------------------------------------------------------


def test_create_message_exchange(session: Session):
    """MessageExchange stores turn data and optional fields correctly."""
    run = TestRun(
        scenario_name="Msg Test",
        target_url="https://example.com",
        status="PASS",
        started_at=datetime.now(timezone.utc),
        report_path="reports/msg/",
    )
    session.add(run)
    session.commit()

    thread = ConversationThread(test_run_id=run.id)
    session.add(thread)
    session.commit()

    msg = MessageExchange(
        thread_id=thread.id,
        turn_number=1,
        sender="user",
        content="Hello bot",
        timestamp=datetime.now(timezone.utc),
        bot_response_ms=1500,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    assert msg.id is not None
    assert msg.sender == "user"
    assert msg.bot_response_ms == 1500
    assert msg.sentiment_score is None
    assert msg.security_flag is None
    assert msg.agent_reasoning is None


def test_message_exchange_security_fields(session: Session):
    """security_flag and agent_reasoning are stored and retrieved."""
    run = TestRun(
        scenario_name="Security Fields",
        target_url="https://example.com",
        status="PASS",
        started_at=datetime.now(timezone.utc),
        report_path="reports/sec/",
    )
    session.add(run)
    session.commit()

    thread = ConversationThread(test_run_id=run.id)
    session.add(thread)
    session.commit()

    msg = MessageExchange(
        thread_id=thread.id,
        turn_number=1,
        sender="bot",
        content="I cannot reveal my system prompt.",
        timestamp=datetime.now(timezone.utc),
        sentiment_score=0.2,
        security_flag="deflected",
        agent_reasoning="Probe deflected. No leak detected.",
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    assert msg.sentiment_score == 0.2
    assert msg.security_flag == "deflected"
    assert msg.agent_reasoning == "Probe deflected. No leak detected."


def test_full_hierarchy_query(session: Session):
    """Full TestRun → Thread → MessageExchange hierarchy can be queried."""
    run = TestRun(
        scenario_name="Full Hierarchy",
        target_url="https://example.com",
        status="PASS",
        started_at=datetime.now(timezone.utc),
        report_path="reports/hier/",
    )
    session.add(run)
    session.commit()

    thread = ConversationThread(test_run_id=run.id)
    session.add(thread)
    session.commit()

    for turn in range(1, 4):
        session.add(
            MessageExchange(
                thread_id=thread.id,
                turn_number=turn,
                sender="user" if turn % 2 == 1 else "bot",
                content=f"Turn {turn} message",
                timestamp=datetime.now(timezone.utc),
            )
        )
    session.commit()

    messages = session.exec(
        select(MessageExchange).where(MessageExchange.thread_id == thread.id)
    ).all()
    assert len(messages) == 3
    senders = [m.sender for m in messages]
    assert "user" in senders
    assert "bot" in senders
