"""SQLite by default, PostgreSQL when DATABASE_URL points at it.

The stored document is the evaluation report produced by the engine.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import JSON

from agentgate.config import find_repo_root
from agentgate.domain import EvaluationReport


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    config_json: Mapped[Dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40))


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[str] = mapped_column(String(40))
    completed_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    baseline_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    candidate_name: Mapped[str] = mapped_column(String(200))
    report_json: Mapped[Dict[str, Any]] = mapped_column(JSON)


class GithubDeliveryRow(Base):
    __tablename__ = "github_deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    repository: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    pull_request: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment_body: Mapped[str] = mapped_column(Text)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))


def default_database_url() -> str:
    override = os.environ.get("AGENTGATE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if override:
        return override
    root = find_repo_root()
    path = root / ".agentgate" / "agentgate.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def make_engine(url: Optional[str] = None):
    database_url = url or default_database_url()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


def make_session_factory(url: Optional[str] = None):
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def save_project(session: Session, name: str, description: str, config: Dict[str, Any], created_at: str) -> ProjectRow:
    existing = session.scalar(select(ProjectRow).where(ProjectRow.name == name))
    if existing:
        existing.description = description
        existing.config_json = config
        session.commit()
        return existing
    row = ProjectRow(
        id=uuid.uuid4().hex,
        name=name,
        description=description,
        config_json=config,
        created_at=created_at,
    )
    session.add(row)
    session.commit()
    return row


def save_run(session: Session, project_id: str, report: EvaluationReport) -> RunRow:
    row = RunRow(
        id=report.manifest.run_id,
        project_id=project_id,
        decision=report.gate.decision,
        started_at=report.manifest.started_at,
        completed_at=report.manifest.completed_at,
        baseline_name=None if report.manifest.baseline is None else report.manifest.baseline.name,
        candidate_name=report.manifest.candidate.name,
        report_json=report.model_dump(mode="json"),
    )
    session.add(row)
    session.commit()
    return row


def list_runs(session: Session, project_id: Optional[str] = None) -> List[RunRow]:
    query = select(RunRow).order_by(RunRow.started_at.desc())
    if project_id:
        query = query.where(RunRow.project_id == project_id)
    return list(session.scalars(query))


def get_run(session: Session, run_id: str) -> Optional[RunRow]:
    return session.get(RunRow, run_id)


def report_of(row: RunRow) -> EvaluationReport:
    return EvaluationReport.model_validate(row.report_json)
