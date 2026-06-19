"""Run orchestrator: discovery -> remediation -> verification."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from . import scanner
from .config import get_settings
from .devin_client import DevinClient
from .models import Finding, RemediationSession, Run, Vertical
from .prompts import discovery_prompt, remediation_prompt
from .store import store

REPO = get_settings().github_repo


def _now() -> datetime:
    return datetime.now(timezone.utc)


_DEMO_FINDINGS: list[Finding] = [
    Finding(
        id="pyjwt",
        vertical=Vertical.SECURITY,
        severity="high",
        title="fix(deps): upgrade PyJWT to 2.13.0 to remediate 5 CVEs",
        target="pyjwt",
        labels=["devin", "security", "high"],
        body="pip-audit flagged PyJWT 2.12.0 (PYSEC-2026-175..179). Auth-critical.",
    ),
    Finding(
        id="flask",
        vertical=Vertical.SECURITY,
        severity="high",
        title="fix(deps): upgrade Flask to 3.1.3 (CVE-2026-27205)",
        target="flask",
        labels=["devin", "security", "high"],
        body="pip-audit flagged Flask 2.3.3 with CVE-2026-27205.",
    ),
    Finding(
        id="paramiko",
        vertical=Vertical.SECURITY,
        severity="moderate",
        title="fix(deps): upgrade paramiko (CVE-2026-44405)",
        target="paramiko",
        labels=["devin", "security", "moderate"],
        body="pip-audit flagged paramiko 3.5.1 with CVE-2026-44405.",
    ),
    Finding(
        id="any-dashboard",
        vertical=Vertical.BACKLOG,
        severity="low",
        title="refactor(types): remove `any` types in src/dashboard/",
        target="superset-frontend/src/dashboard",
        labels=["devin", "backlog", "code-quality"],
        body="Replace `any` usages with explicit TypeScript types (1,139 occurrences in this directory).",
    ),
    Finding(
        id="any-explore",
        vertical=Vertical.BACKLOG,
        severity="low",
        title="refactor(types): remove `any` types in src/explore/",
        target="superset-frontend/src/explore",
        labels=["devin", "backlog", "code-quality"],
        body="Replace `any` usages with explicit TypeScript types in the explore module.",
    ),
    Finding(
        id="sqla-2.0",
        vertical=Vertical.BACKLOG,
        severity="low",
        title="refactor: migrate legacy .query() to SQLAlchemy 2.0 select()",
        target="superset/daos",
        labels=["devin", "backlog", "code-quality"],
        body="Migrate a module from legacy .query() to 2.0 select() syntax.",
    ),
]


def _demo_findings(vertical: Vertical) -> list[Finding]:
    out = []
    for f in _DEMO_FINDINGS:
        if vertical == Vertical.BOTH or f.vertical == vertical:
            copy = f.model_copy()
            copy.issue_url = f"https://github.com/{REPO}/issues/{abs(hash(f.id)) % 900 + 100}"
            out.append(copy)
    return out


# Live orchestration tasks, keyed by run id, so a run can be cancelled.
_tasks: dict[str, asyncio.Task] = {}


def create_run(vertical: Vertical) -> Run:
    run = Run(
        id=f"run-{uuid.uuid4().hex[:8]}",
        vertical=vertical,
        created_at=_now(),
        updated_at=_now(),
    )
    store.save(run)
    _tasks[run.id] = asyncio.create_task(_drive(run.id))
    return run


async def stop_run(run_id: str) -> Run | None:
    """Cancel orchestration and archive every live Devin session in the run."""
    run = store.get(run_id)
    if not run:
        return None

    # 1. Stop the orchestrator: no more polling or new sessions get spawned.
    task = _tasks.pop(run_id, None)
    if task and not task.done():
        task.cancel()

    # 2. Archive every Devin session that isn't already terminal (stops ACUs).
    if not get_settings().demo_mode:
        client = DevinClient()
        ids = [run.discovery_session_id] + [s.session_id for s in run.sessions]
        await asyncio.gather(
            *(_archive(client, sid) for sid in ids if sid), return_exceptions=True
        )

    # 3. Mark the run + any unfinished sessions as stopped.
    for s in run.sessions:
        if s.status in ("pending", "working", "blocked"):
            s.status = "stopped"
            s.finished_at = _now()
    run.phase = "stopped"
    run.updated_at = _now()
    store.save(run)
    return run


async def _archive(client: DevinClient, session_id: str) -> None:
    try:
        await client.archive_session(session_id)
    except Exception:  # noqa: BLE001 - best-effort; session may already be idle
        pass


async def _drive(run_id: str) -> None:
    s = get_settings()
    run = store.get(run_id)
    if not run:
        return
    try:
        run.before = scanner.snapshot()
        store.save(run)
        if s.demo_mode:
            # _drive_demo computes its own before/after impact delta.
            await _drive_demo(run)
        else:
            await _drive_live(run)
            run.after = scanner.snapshot()
        run.phase = "completed"
    except Exception as exc:
        run.phase = "failed"
        run.error = str(exc)
    run.updated_at = _now()
    store.save(run)


async def _drive_live(run: Run) -> None:
    s = get_settings()
    client = DevinClient()

    # Phase 1: discovery session creates GitHub issues + returns findings.
    disc = await client.create_session(
        discovery_prompt(run.vertical),
        title=f"[{run.id}] discovery ({run.vertical.value})",
        tags=["devin-automation", "discovery", run.id],
    )
    run.discovery_session_id = disc.get("session_id")
    run.discovery_session_url = disc.get("url")
    run.phase = "discovering"
    store.save(run)

    payload = await _poll(client, run.discovery_session_id)
    disc_blob = await _message_blob(client, run.discovery_session_id)
    findings = _parse_findings(client, payload, disc_blob)[: s.max_sessions_per_run]
    run.findings = findings
    run.phase = "remediating"
    store.save(run)

    # Phase 2: one remediation session per finding, polled concurrently.
    run.sessions = [
        RemediationSession(
            finding_id=f.id,
            finding_title=f.title,
            vertical=f.vertical,
            status="pending",
        )
        for f in findings
    ]
    store.save(run)
    await asyncio.gather(
        *(_remediate(client, run, f, i) for i, f in enumerate(findings))
    )


async def _remediate(client: DevinClient, run: Run, finding: Finding, idx: int) -> None:
    sess = run.sessions[idx]
    created = await client.create_session(
        remediation_prompt(finding.title, finding.body, finding.target, finding.issue_url),
        title=f"[{run.id}] fix: {finding.title[:60]}",
        tags=["devin-automation", "fix", run.id],
    )
    sess.session_id = created.get("session_id")
    sess.session_url = created.get("url")
    sess.status = "working"
    sess.started_at = _now()
    store.save(run)

    payload = await _poll(client, sess.session_id)
    blob = await _message_blob(client, sess.session_id)
    result = client.extract_structured(payload) or client.extract_json_from_text(blob) or {}
    sess.pr_url = client.extract_pr_url(payload, blob) or result.get("pr_url")
    sess.tests_pass = result.get("tests_pass")
    # Failing/unrun tests -> draft PR (per the remediation prompt's gate).
    sess.is_draft = result.get("is_draft")
    if sess.is_draft is None and sess.tests_pass is False:
        sess.is_draft = True
    sess.summary = result.get("summary", "")
    # A session that produced a PR is a success even if Devin idles afterward.
    sess.status = "finished" if sess.pr_url else client.session_state(payload)
    sess.finished_at = _now()
    store.save(run)


async def _poll(client: DevinClient, session_id: str | None) -> dict:
    """Poll a session until it stops working. Bounded to avoid infinite loops."""
    s = get_settings()
    if not session_id:
        return {}
    max_iters = max(1, int(3600 / max(s.poll_interval, 1)))  # ~1h ceiling
    payload: dict = {}
    for _ in range(max_iters):
        payload = await client.get_session(session_id)
        if client.is_terminal(payload):
            return payload
        await asyncio.sleep(s.poll_interval)
    return payload


async def _message_blob(client: DevinClient, session_id: str | None) -> str:
    if not session_id:
        return ""
    try:
        msgs = await client.get_messages(session_id)
        return "\n".join(
            str(m.get("message", m.get("content", ""))) for m in msgs
        )
    except Exception:
        return ""


def _parse_findings(client: DevinClient, payload: dict, blob: str = "") -> list[Finding]:
    # Prefer structured_output; fall back to a fenced JSON block in messages.
    data = (
        client.extract_structured(payload)
        or client.extract_json_from_text(blob)
        or {}
    )
    raw = data.get("findings", [])
    findings = []
    for i, item in enumerate(raw):
        findings.append(
            Finding(
                id=item.get("target", f"finding-{i}").replace("/", "-"),
                vertical=Vertical(item.get("vertical", "backlog")),
                severity=item.get("severity", "moderate"),
                title=item.get("title", "Untitled finding"),
                body=item.get("body", ""),
                labels=item.get("labels", []),
                target=item.get("target", ""),
                issue_url=item.get("issue_url"),
            )
        )
    return findings


async def _drive_demo(run: Run) -> None:
    run.discovery_session_url = f"https://app.devin.ai/sessions/demo-{run.id}"
    run.phase = "discovering"
    store.save(run)
    await asyncio.sleep(3)  # discovery "runs"

    findings = _demo_findings(run.vertical)[: get_settings().max_sessions_per_run]
    run.findings = findings
    run.sessions = [
        RemediationSession(
            finding_id=f.id,
            finding_title=f.title,
            vertical=f.vertical,
            session_id=f"devin-demo-{f.id}",
            session_url=f"https://app.devin.ai/sessions/demo-{f.id}",
            status="pending",
        )
        for f in findings
    ]
    run.phase = "remediating"
    store.save(run)

    await asyncio.gather(*(_remediate_demo(run, i) for i in range(len(findings))))

    # Simulate the impact delta the post-merge re-scan would reveal.
    if run.before:
        run.after = run.before.model_copy()
        fixed = sum(1 for f in findings if f.vertical == Vertical.SECURITY)
        if run.after.py_vulns is not None:
            run.after.py_vulns = max(0, run.after.py_vulns - fixed)
        elif run.before.py_vulns is None:
            # No local repo mounted: fabricate a believable before/after.
            run.before.py_vulns = 11
            run.after.py_vulns = max(0, 11 - fixed)


async def _remediate_demo(run: Run, idx: int) -> None:
    sess = run.sessions[idx]
    finding = run.findings[idx]
    sess.status = "working"
    sess.started_at = _now()
    store.save(run)

    # Stagger completion so the dashboard shows live progress.
    await asyncio.sleep(4 + idx * 3)

    # One finding "fails" tests to exercise the failure path in observability.
    fails = finding.id == "any-explore"
    sess.status = "finished"
    sess.tests_pass = not fails
    sess.is_draft = fails  # failing tests -> draft PR
    sess.pr_url = f"https://github.com/{REPO}/pull/{abs(hash(finding.id)) % 900 + 100}"
    sess.summary = (
        "Upgraded dependency and verified test suite"
        if finding.vertical == Vertical.SECURITY
        else "Replaced any-types with explicit types"
    )
    sess.finished_at = _now()
    store.save(run)
