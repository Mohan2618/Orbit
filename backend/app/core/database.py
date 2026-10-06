"""Database engine and request-scoped SQLAlchemy sessions."""

from collections.abc import Generator
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url
    postgres_host = os.getenv("POSTGRES_HOST")
    if postgres_host:
        return URL.create(
            "postgresql+psycopg",
            username=os.getenv("POSTGRES_USER", "orbit"),
            password=os.getenv("POSTGRES_PASSWORD", "orbit-local-only"),
            host=postgres_host,
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "orbit"),
        ).render_as_string(hide_password=False)
    return "sqlite:///./orbit.db"


DATABASE_URL = database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite:") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
