"""ORM model classes and validation constants for llm-tracker."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


metadata = Base.metadata


class BaseUrl(Base):
    __tablename__ = "base_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    provider_name: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    usages: Mapped[list["Usage"]] = relationship(back_populates="base_url")


class Usage(Base):
    __tablename__ = "usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    client_source: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_length: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_creation_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0, server_default=text("0")
    )
    output_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0, server_default=text("0")
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0, server_default=text("0")
    )
    status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_url_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("base_urls.id"), nullable=True
    )
    base_url: Mapped[BaseUrl | None] = relationship(back_populates="usages")


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    client_source: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("''")
    )
    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    reasoning_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cached_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    tool_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cache_creation_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    prompt_length: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    input_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    output_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    successful_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failed_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    latency_sum_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status_429: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status_4xx: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status_5xx: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status_unknown: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )


class SessionRecord(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    client_source: Mapped[str | None] = mapped_column(String, nullable=True)
    started: Mapped[str] = mapped_column(String, nullable=False)
    ended: Mapped[str] = mapped_column(String, nullable=False)
    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    successful_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    failed_requests: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    cached_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, server_default=text("0")
    )
    latency_sum_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    avg_latency_ms: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    avg_ttft_ms: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    primary_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_model: Mapped[str | None] = mapped_column(String, nullable=True)
    providers_json: Mapped[str | None] = mapped_column(String, nullable=True)
    models_json: Mapped[str | None] = mapped_column(String, nullable=True)
    last_usage_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


VALID_OUTCOMES = {"solved", "partial", "failed", "stuck", "no_op", "unknown"}
VALID_SOURCES = {"manual", "heuristic", "llm"}


class SessionEvaluation(Base):
    __tablename__ = "session_evaluations"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    outcome: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'unknown'")
    )
    source: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'manual'")
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    task_title: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
