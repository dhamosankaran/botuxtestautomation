"""Shared pytest fixtures for BOTTestAutomation test suite."""
import pytest
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(name="engine")
def engine_fixture():
    """In-memory SQLite engine, isolated for each test."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture(engine):
    """Database session bound to the in-memory engine."""
    with Session(engine) as session:
        yield session
