"""Pydantic models describing runs, findings, and Devin-backed sessions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Vertical(str, Enum):
    """The two value streams this system automates."""

    SECURITY = "security"  # urgent: fix before it bites (CVEs, vulnerable deps)
    BACKLOG = "backlog"  # toil: trivial, never prioritized (any-types, SQLA 2.0)
    BOTH = "both"


SessionStatus = Literal[
    "pending", "working", "blocked", "finished", "failed", "expired", "stopped"
]


class Finding(BaseModel):
    """One discovered, independently-remediable unit of work."""

    id: str
    vertical: Vertical
    severity: str = "moderate"  # critical | high | moderate | low
    title: str
    body: str = ""
    labels: list[str] = Field(default_factory=list)
    target: str = ""  # package name or path the fix touches
    issue_url: Optional[str] = None  # GitHub issue created for this finding


class RemediationSession(BaseModel):
    """A Devin session tasked with fixing exactly one finding."""

    finding_id: str
    finding_title: str
    vertical: Vertical
    session_id: Optional[str] = None
    session_url: Optional[str] = None
    status: SessionStatus = "pending"
    pr_url: Optional[str] = None
    tests_pass: Optional[bool] = None
    summary: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ScanSnapshot(BaseModel):
    """Deterministic counts used for before/after proof of impact."""

    npm_vulns: Optional[int] = None
    py_vulns: Optional[int] = None
    any_types: Optional[int] = None
    sqla_legacy: Optional[int] = None
    taken_at: Optional[datetime] = None


class Run(BaseModel):
    """A single button-click invocation of the remediation pipeline."""

    id: str
    vertical: Vertical
    phase: Literal[
        "discovering", "remediating", "completed", "failed", "stopped"
    ] = "discovering"
    created_at: datetime
    updated_at: datetime
    discovery_session_id: Optional[str] = None
    discovery_session_url: Optional[str] = None
    findings: list[Finding] = Field(default_factory=list)
    sessions: list[RemediationSession] = Field(default_factory=list)
    before: Optional[ScanSnapshot] = None
    after: Optional[ScanSnapshot] = None
    error: Optional[str] = None


class CreateRunRequest(BaseModel):
    vertical: Vertical = Vertical.BOTH


class Metrics(BaseModel):
    """Aggregate KPIs answering 'how do I know this is working?'"""

    total_runs: int = 0
    findings_discovered: int = 0
    sessions_started: int = 0
    prs_opened: int = 0
    succeeded: int = 0
    failed: int = 0
    in_progress: int = 0
    success_rate: float = 0.0
    vulns_remediated: int = 0  # before - after, summed across runs
    backlog_fixed: int = 0  # succeeded backlog (code-quality) sessions
