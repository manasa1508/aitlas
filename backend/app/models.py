from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


def new_id() -> str:
    return str(uuid4())


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(1000))
    kind: Mapped[str] = mapped_column(String(24))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    next_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_count: Mapped[int] = mapped_column(Integer, default=0)


class Item(Base):
    __tablename__ = "items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1500), unique=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    score: Mapped[float] = mapped_column(Float, default=0)
    title_fingerprint: Mapped[str] = mapped_column(String(300), index=True)
    source: Mapped[Source] = relationship()

    __table_args__ = (Index("ix_items_kind_published", "kind", "published_at"),)


class Knowledge(Base):
    __tablename__ = "knowledge"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    year: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    summary: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(1500))
    source_label: Mapped[str] = mapped_column(String(200))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    related_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    industry: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text)
    website: Mapped[str] = mapped_column(String(500))
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(1500))
    source_label: Mapped[str] = mapped_column(String(200))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[Company] = relationship(back_populates="evidence")


class UseCase(Base):
    __tablename__ = "use_cases"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(300))
    industry: Mapped[str] = mapped_column(String(100), index=True)
    domain: Mapped[str] = mapped_column(String(100), index=True)
    summary: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(String(1500))
    evidence_label: Mapped[str] = mapped_column(String(200))
    maturity: Mapped[str] = mapped_column(String(40))
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    company: Mapped[Company | None] = relationship()


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    industry: Mapped[str] = mapped_column(String(100), index=True)
    capability: Mapped[str] = mapped_column(String(100))
    thesis: Mapped[str] = mapped_column(Text)
    barrier: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[str] = mapped_column(String(1500))
    evidence_label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="hypothesis")


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list)
