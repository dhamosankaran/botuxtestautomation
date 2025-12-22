"""Database configuration and session management."""
from sqlmodel import create_engine, Session, SQLModel

DATABASE_URL = "sqlite:///./results.db"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables():
    """Create database and all tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session
