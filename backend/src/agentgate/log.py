"""Structured JSON logs for one evaluation run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TextIO


class RunLog:
    def __init__(self, run_id: str, stream: Optional[TextIO] = None) -> None:
        self.run_id = run_id
        self.stream = stream
        self.records: List[Dict[str, Any]] = []

    def event(self, event: str, **fields: Any) -> None:
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": fields.pop("level", "info"),
            "run_id": self.run_id,
            "event": event,
        }
        record.update(fields)
        self.records.append(record)
        if self.stream is not None:
            self.stream.write(json.dumps(record, default=str) + "\n")
            self.stream.flush()
