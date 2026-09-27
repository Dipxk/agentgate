"""GitHub comment delivery.

The comment body is rendered from a measured report. This module posts it.
It does not calculate metrics.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from agentgate.domain import EvaluationReport
from agentgate.errors import ConfigError
from agentgate.report import render_github_comment


def build_comment(report: EvaluationReport, dashboard_url: Optional[str]) -> str:
    return render_github_comment(report, dashboard_url=dashboard_url or None)


def post_pull_request_comment(
    repository: str,
    pull_number: int,
    body: str,
    token: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> dict:
    secret = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
    if not secret:
        raise ConfigError("GITHUB_TOKEN is not set. The comment was not posted.")
    if "/" not in repository:
        raise ConfigError("repository must look like owner/name")
    owns_client = client is None
    http = client or httpx.Client(timeout=20)
    try:
        response = http.post(
            f"https://api.github.com/repos/{repository}/issues/{pull_number}/comments",
            headers={
                "Authorization": f"Bearer {secret}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"body": body},
        )
    finally:
        if owns_client:
            http.close()
    if response.status_code >= 400:
        raise ConfigError(f"GitHub returned HTTP {response.status_code} and the comment was not posted.")
    return response.json()
