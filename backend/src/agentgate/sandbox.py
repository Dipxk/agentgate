"""Docker sandbox for dataset-authored tests.

The test source comes from the evaluation dataset, which is trusted project
configuration. Model output is passed in as data and is not executed.
If Docker is missing or the container fails to start, the result is an
infrastructure error, not an agent failure.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


RUNNER = r"""
import json
import pathlib
import traceback

payload = json.loads(pathlib.Path("/work/payload.json").read_text())
outcome = payload.get("outcome")
output = payload.get("output")
tool_calls = payload.get("tool_calls") or []
namespace = {"outcome": outcome, "output": output, "tool_calls": tool_calls}
try:
    exec(compile(pathlib.Path("/work/test_case.py").read_text(), "test_case.py", "exec"), namespace, namespace)
except Exception:
    result = {"passed": False, "detail": traceback.format_exc(limit=3)}
else:
    result = {"passed": True, "detail": "deterministic test passed"}
print(json.dumps(result))
"""


class SandboxLimits(BaseModel):
    memory: str = "128m"
    cpus: float = Field(default=0.5, gt=0)
    pids: int = Field(default=64, gt=0)
    timeout_s: float = Field(default=15, gt=0)
    image: str = "python:3.12-slim"


class SandboxResult(BaseModel):
    status: str  # pass, fail, infrastructure_error
    detail: str


def docker_argv(limits: SandboxLimits, workdir: Path) -> List[str]:
    """Build a non-privileged, non-networked container command."""

    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        limits.memory,
        "--cpus",
        str(limits.cpus),
        "--pids-limit",
        str(limits.pids),
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        "-v",
        f"{workdir}:/work:ro",
        limits.image,
        "python",
        "-I",
        "-B",
        "-c",
        RUNNER,
    ]


class DockerSandbox:
    def __init__(self, limits: Optional[SandboxLimits] = None) -> None:
        self.limits = limits or SandboxLimits()

    def run(self, source: str, payload: Dict[str, Any]) -> SandboxResult:
        if shutil.which("docker") is None:
            return SandboxResult(
                status="infrastructure_error",
                detail=(
                    "Docker is not installed. The code evaluator did not run and "
                    "was not scored as an agent failure."
                ),
            )
        try:
            with tempfile.TemporaryDirectory(prefix="agentgate-") as directory:
                workdir = Path(directory)
                (workdir / "test_case.py").write_text(source)
                (workdir / "payload.json").write_text(json.dumps(payload))
                command = docker_argv(self.limits, workdir)
                try:
                    completed = subprocess.run(
                        command,
                        capture_output=True,
                        text=True,
                        timeout=self.limits.timeout_s,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    return SandboxResult(
                        status="infrastructure_error",
                        detail=f"Docker test exceeded {self.limits.timeout_s}s and was stopped.",
                    )
                except OSError as exc:
                    return SandboxResult(
                        status="infrastructure_error",
                        detail=f"Docker failed to start: {exc}",
                    )
                stdout = (completed.stdout or "").strip()
                if completed.returncode != 0 or not stdout:
                    stderr = (completed.stderr or "").strip()
                    return SandboxResult(
                        status="infrastructure_error",
                        detail=f"Docker exited {completed.returncode}. {stderr[:500]}".strip(),
                    )
                try:
                    parsed = json.loads(stdout.splitlines()[-1])
                except (json.JSONDecodeError, IndexError):
                    return SandboxResult(
                        status="infrastructure_error",
                        detail="Sandbox did not return a JSON result.",
                    )
                if parsed.get("passed") is True:
                    return SandboxResult(status="pass", detail=str(parsed.get("detail") or "passed"))
                return SandboxResult(status="fail", detail=str(parsed.get("detail") or "test failed"))
        except OSError as exc:
            return SandboxResult(
                status="infrastructure_error",
                detail=f"Could not prepare the sandbox: {exc}",
            )
