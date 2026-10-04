from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Settings(BaseSettings):
    database_url: str = "sqlite:///./aitlas.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    ollama_url: str = ""
    ollama_model: str = ""
    github_token: str = ""
    ca_bundle_path: str = ""
    ca_cert_base64: str = ""
    worker_tick_seconds: int = 60
    user_agent: str = "AItlas/0.1 (local research aggregator; contact: local operator)"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    # Schema changes after V1 must use versioned migrations. This creates the initial schema.
    from . import models  # noqa: F401

    if settings.database_url.startswith("sqlite"):
        path = settings.database_url.removeprefix("sqlite:///")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
