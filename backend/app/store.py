"""In-memory run store with JSON persistence."""

from __future__ import annotations

import json
import os
from typing import Optional

from .models import Metrics, Run

_STATE_FILE = os.environ.get("STATE_FILE", "/tmp/devin_runs.json")


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(_STATE_FILE):
            try:
                with open(_STATE_FILE) as f:
                    data = json.load(f)
                for rid, raw in data.items():
                    self._runs[rid] = Run.model_validate(raw)
            except Exception:
                self._runs = {}

    def _persist(self) -> None:
        try:
            with open(_STATE_FILE, "w") as f:
                json.dump(
                    {rid: r.model_dump(mode="json") for rid, r in self._runs.items()},
                    f,
                    default=str,
                )
        except Exception:
            pass

    def save(self, run: Run) -> None:
        self._runs[run.id] = run
        self._persist()

    def get(self, run_id: str) -> Optional[Run]:
        return self._runs.get(run_id)

    def list(self) -> list[Run]:
        return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)

    def metrics(self) -> Metrics:
        m = Metrics(total_runs=len(self._runs))
        for run in self._runs.values():
            m.findings_discovered += len(run.findings)
            for s in run.sessions:
                m.sessions_started += 1
                if s.pr_url:
                    m.prs_opened += 1
                if s.status in ("failed", "expired"):
                    m.failed += 1
                elif s.status == "finished":
                    # A finished session whose tests failed is not a success.
                    if s.tests_pass is False:
                        m.failed += 1
                    else:
                        m.succeeded += 1
                elif s.status in ("pending", "working", "blocked"):
                    m.in_progress += 1
            if run.before and run.after:
                before = (run.before.npm_vulns or 0) + (run.before.py_vulns or 0)
                after = (run.after.npm_vulns or 0) + (run.after.py_vulns or 0)
                m.vulns_remediated += max(0, before - after)
        done = m.succeeded + m.failed
        m.success_rate = round(m.succeeded / done, 3) if done else 0.0
        return m


store = RunStore()
