import json
from pathlib import Path

from fastapi.testclient import TestClient

from agentgate.api import create_app
from agentgate.github_api import post_pull_request_comment
from agentgate.service import run_project
from tests.conftest import ROOT


def test_api_serves_a_measured_run(tmp_path: Path):
    database = tmp_path / "agentgate.db"
    app = create_app(f"sqlite:///{database}")
    client = TestClient(app)
    report = run_project(root=ROOT, candidate_path=ROOT / "evaluation/agents/regressed.yaml")
    from agentgate.storage import make_session_factory, save_project, save_run
    from datetime import datetime, timezone

    factory = make_session_factory(f"sqlite:///{database}")
    with factory() as db:
        project = save_project(
            db,
            "support-demo",
            "synthetic",
            {"gates": "evaluation/gates/default.yaml", "versions": []},
            datetime.now(timezone.utc).isoformat(),
        )
        save_run(db, project.id, report)

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    overview = client.get("/api/v1/overview").json()
    assert overview["runs"] == 1
    assert overview["decisions"]["block"] == 1
    assert overview["mean_candidate_accuracy"] == report.candidate_metrics.accuracy
    assert overview["mean_candidate_cost_usd"] is None

    detail = client.get(f"/api/v1/runs/{report.manifest.run_id}").json()
    assert detail["decision"] == "block"
    assert detail["candidate_metrics"]["accuracy"] == report.candidate_metrics.accuracy
    case = client.get(f"/api/v1/runs/{report.manifest.run_id}/cases/support-008").json()
    assert case["candidate"]["status"] == "failed"
    assert case["comparison"]["change"] == "regression"
    missing = client.get(f"/api/v1/runs/{report.manifest.run_id}/cases/missing")
    assert missing.status_code == 404


def test_api_rejects_a_path_that_escapes_the_repo(tmp_path: Path):
    database = tmp_path / "agentgate.db"
    app = create_app(f"sqlite:///{database}")
    client = TestClient(app)
    from datetime import datetime, timezone

    from agentgate.storage import make_session_factory, save_project

    factory = make_session_factory(f"sqlite:///{database}")
    with factory() as db:
        project = save_project(db, "support-demo", "synthetic", {}, datetime.now(timezone.utc).isoformat())
    response = client.post(
        f"/api/v1/projects/{project.id}/evaluate",
        json={"candidate": "../../etc/passwd"},
    )
    assert response.status_code == 400
    assert "escapes" in response.json()["detail"]


def test_github_comment_is_not_posted_without_a_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("GitHub should not be called without a token")

    from agentgate.errors import ConfigError
    import pytest

    with pytest.raises(ConfigError, match="GITHUB_TOKEN"):
        post_pull_request_comment("acme/widgets", 1, "hello", token="", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_github_comment_posts_the_rendered_body():
    import httpx

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(201, json={"id": 9})

    result = post_pull_request_comment(
        "acme/widgets",
        12,
        "decision body",
        token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert result["id"] == 9
    assert seen["url"].endswith("/repos/acme/widgets/issues/12/comments")
    assert seen["body"]["body"] == "decision body"
