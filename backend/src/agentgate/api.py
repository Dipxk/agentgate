"""HTTP API over the same evaluation engine the CLI uses."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agentgate import __version__
from agentgate.config import find_repo_root, load_gates, resolve_inside
from agentgate.domain import EvaluationReport
from agentgate.errors import AgentGateError
from agentgate.github_api import build_comment, post_pull_request_comment
from agentgate.service import replay_project, run_project
from agentgate.storage import (
    GithubDeliveryRow,
    ProjectRow,
    get_run,
    list_runs,
    make_session_factory,
    report_of,
    save_run,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvaluateIn(BaseModel):
    baseline: Optional[str] = None
    candidate: Optional[str] = None
    trials: Optional[int] = Field(default=None, ge=1, le=20)
    seed: Optional[int] = None
    baseline_commit: Optional[str] = None
    candidate_commit: Optional[str] = None


class DeliveryIn(BaseModel):
    run_id: str
    repository: Optional[str] = None
    pull_request: Optional[int] = None
    dashboard_url: Optional[str] = None
    post: bool = False


def create_app(database_url: Optional[str] = None) -> FastAPI:
    factory = make_session_factory(database_url)
    app = FastAPI(title="AgentGate", version=__version__)
    origins = os.environ.get("AGENTGATE_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in origins if origin.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def session():
        return factory()

    @app.get("/api/v1/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/overview")
    def overview() -> Dict[str, Any]:
        with session() as db:
            projects = list(db.query(ProjectRow).all())
            rows = list_runs(db)
            reports = [report_of(row) for row in rows]
        return _overview(projects, rows, reports)

    @app.get("/api/v1/projects")
    def projects() -> List[Dict[str, Any]]:
        with session() as db:
            return [_project_summary(row) for row in db.query(ProjectRow).order_by(ProjectRow.created_at.desc())]

    @app.get("/api/v1/projects/{project_id}")
    def project_detail(project_id: str) -> Dict[str, Any]:
        with session() as db:
            row = db.get(ProjectRow, project_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Project not found")
            runs = list_runs(db, project_id)
            payload = _project_summary(row)
            payload["runs"] = [_run_summary(item, report_of(item)) for item in runs]
            payload["gates"] = _gate_document(row)
            return payload

    @app.post("/api/v1/projects/{project_id}/evaluate")
    def evaluate_project(project_id: str, body: EvaluateIn) -> Dict[str, Any]:
        with session() as db:
            row = db.get(ProjectRow, project_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Project not found")
            root = find_repo_root()
            try:
                baseline = resolve_inside(root, body.baseline) if body.baseline else None
                candidate = resolve_inside(root, body.candidate) if body.candidate else None
                report = run_project(
                    root=root,
                    baseline_path=baseline,
                    candidate_path=candidate,
                    trials=body.trials,
                    seed=body.seed,
                    baseline_commit=body.baseline_commit,
                    candidate_commit=body.candidate_commit,
                )
            except AgentGateError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            save_run(db, row.id, report)
            return {"run_id": report.manifest.run_id, "decision": report.gate.decision}

    @app.get("/api/v1/runs")
    def runs() -> List[Dict[str, Any]]:
        with session() as db:
            return [_run_summary(row, report_of(row)) for row in list_runs(db)]

    @app.get("/api/v1/runs/{run_id}")
    def run_detail(run_id: str) -> Dict[str, Any]:
        report, row = _load(session, run_id)
        summary = _run_summary(row, report)
        summary["report"] = report.model_dump(mode="json")
        return summary

    @app.get("/api/v1/runs/{run_id}/cases/{case_id}")
    def case_detail(run_id: str, case_id: str) -> Dict[str, Any]:
        report, _row = _load(session, run_id)
        baseline = [
            item.model_dump(mode="json")
            for item in report.case_results
            if item.case_id == case_id and item.side == "baseline" and item.trial == 1
        ]
        candidate = [
            item.model_dump(mode="json")
            for item in report.case_results
            if item.case_id == case_id and item.side == "candidate" and item.trial == 1
        ]
        if not baseline and not candidate:
            raise HTTPException(status_code=404, detail="Case not found in this run")
        comparison = next((item for item in report.comparisons if item.case_id == case_id), None)
        return {
            "run_id": run_id,
            "case_id": case_id,
            "comparison": None if comparison is None else comparison.model_dump(mode="json"),
            "baseline": baseline[0] if baseline else None,
            "candidate": candidate[0] if candidate else None,
        }

    @app.post("/api/v1/runs/{run_id}/replay")
    def replay(run_id: str) -> Dict[str, Any]:
        report, row = _load(session, run_id)
        try:
            replayed = replay_project(report)
        except AgentGateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with session() as db:
            save_run(db, row.project_id, replayed)
        return {"run_id": replayed.manifest.run_id, "decision": replayed.gate.decision}

    @app.get("/api/v1/runs/{run_id}/comment")
    def comment(run_id: str, dashboard_url: Optional[str] = None) -> Dict[str, str]:
        report, _row = _load(session, run_id)
        return {"body": build_comment(report, dashboard_url)}

    @app.get("/api/v1/compare")
    def compare(a: str, b: str) -> Dict[str, Any]:
        left, _ = _load(session, a)
        right, _ = _load(session, b)
        return {
            "note": "This comparison shows stored measurements. It does not create a new release decision.",
            "a": _compare_side(left),
            "b": _compare_side(right),
        }

    @app.get("/api/v1/github")
    def github() -> Dict[str, Any]:
        with session() as db:
            deliveries = list(db.query(GithubDeliveryRow).order_by(GithubDeliveryRow.created_at.desc()).limit(10))
        return {
            "token_configured": bool(os.environ.get("GITHUB_TOKEN")),
            "deliveries": [
                {
                    "id": item.id,
                    "run_id": item.run_id,
                    "repository": item.repository,
                    "pull_request": item.pull_request,
                    "delivered": item.delivered,
                    "created_at": item.created_at,
                    "comment_body": item.comment_body,
                }
                for item in deliveries
            ],
        }

    @app.post("/api/v1/github/deliveries")
    def deliver(body: DeliveryIn) -> Dict[str, Any]:
        report, _row = _load(session, body.run_id)
        comment_body = build_comment(report, body.dashboard_url)
        delivered = False
        if body.post:
            if not body.repository or body.pull_request is None:
                raise HTTPException(status_code=400, detail="repository and pull_request are required to post")
            try:
                post_pull_request_comment(body.repository, body.pull_request, comment_body)
            except AgentGateError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            delivered = True
        with session() as db:
            row = GithubDeliveryRow(
                id=os.urandom(8).hex(),
                run_id=body.run_id,
                repository=body.repository,
                pull_request=body.pull_request,
                comment_body=comment_body,
                delivered=delivered,
                created_at=_now(),
            )
            db.add(row)
            db.commit()
            delivery_id = row.id
        return {"id": delivery_id, "delivered": delivered}

    return app


def _load(factory, run_id: str):
    with factory() as db:
        row = get_run(db, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return report_of(row), row


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _overview(projects: List[ProjectRow], rows, reports: List[EvaluationReport]) -> Dict[str, Any]:
    accuracies = [item.candidate_metrics.accuracy for item in reports if item.candidate_metrics.accuracy is not None]
    latencies = [
        item.candidate_metrics.median_latency_ms
        for item in reports
        if item.candidate_metrics.median_latency_ms is not None
    ]
    costs = [
        item.candidate_metrics.average_cost_usd
        for item in reports
        if item.candidate_metrics.cost_status == "measured" and item.candidate_metrics.average_cost_usd is not None
    ]
    return {
        "projects": len(projects),
        "runs": len(reports),
        "decisions": {
            "pass": sum(1 for item in reports if item.gate.decision == "pass"),
            "review": sum(1 for item in reports if item.gate.decision == "review"),
            "block": sum(1 for item in reports if item.gate.decision == "block"),
        },
        "mean_candidate_accuracy": _mean(accuracies),
        "mean_candidate_median_latency_ms": _mean(latencies),
        "mean_candidate_cost_usd": _mean(costs),
        "cost_runs_measured": len(costs),
        "recent_runs": [_run_summary(row, report) for row, report in list(zip(rows, reports))[:8]],
        "regressions": [
            _run_summary(row, report)
            for row, report in zip(rows, reports)
            if report.gate.decision == "block"
        ][:8],
    }


def _project_summary(row: ProjectRow) -> Dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "created_at": row.created_at,
        "config": row.config_json,
    }


def _gate_document(row: ProjectRow) -> Optional[Dict[str, Any]]:
    relative = (row.config_json or {}).get("gates")
    if not relative:
        return None
    try:
        path = resolve_inside(find_repo_root(), relative)
        return load_gates(path).model_dump(mode="json")
    except AgentGateError:
        return None


def _run_summary(row, report: EvaluationReport) -> Dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "decision": report.gate.decision,
        "inconclusive": report.gate.inconclusive,
        "started_at": report.manifest.started_at,
        "completed_at": report.manifest.completed_at,
        "baseline": None if report.manifest.baseline is None else report.manifest.baseline.model_dump(mode="json"),
        "candidate": report.manifest.candidate.model_dump(mode="json"),
        "baseline_metrics": None
        if report.baseline_metrics is None
        else report.baseline_metrics.model_dump(mode="json"),
        "candidate_metrics": report.candidate_metrics.model_dump(mode="json"),
        "variance": report.variance.model_dump(mode="json"),
        "reasons": report.gate.reasons,
    }


def _compare_side(report: EvaluationReport) -> Dict[str, Any]:
    return {
        "run_id": report.manifest.run_id,
        "decision": report.gate.decision,
        "baseline": None if report.manifest.baseline is None else report.manifest.baseline.model_dump(mode="json"),
        "candidate": report.manifest.candidate.model_dump(mode="json"),
        "candidate_metrics": report.candidate_metrics.model_dump(mode="json"),
        "gate": report.gate.model_dump(mode="json"),
    }


app = create_app()
