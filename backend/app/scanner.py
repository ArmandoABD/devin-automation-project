"""Local scanners for before/after vulnerability and code-quality metrics."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

from .config import get_settings
from .models import ScanSnapshot


def _run(cmd: list[str], cwd: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=300
        )
        return proc.returncode, proc.stdout
    except Exception:
        return -1, ""


def _npm_vuln_count(repo: str) -> int | None:
    fe = f"{repo}/superset-frontend"
    _, out = _run(["npm", "audit", "--json"], fe)
    if not out:
        return None
    try:
        data = json.loads(out)
        return data.get("metadata", {}).get("vulnerabilities", {}).get("total")
    except json.JSONDecodeError:
        return None


def _py_vuln_count(repo: str) -> int | None:
    _, out = _run(
        ["pip-audit", "-r", "requirements/base.txt", "--format", "json"], repo
    )
    if not out:
        return None
    try:
        data = json.loads(out)
        deps = data.get("dependencies", data) if isinstance(data, dict) else data
        return sum(len(d.get("vulns", [])) for d in deps)
    except (json.JSONDecodeError, AttributeError):
        return None


def _grep_count(repo: str, pattern: str, path: str) -> int | None:
    code, out = _run(
        ["grep", "-rohE", pattern, f"{repo}/{path}", "--include=*.ts", "--include=*.tsx"],
        repo,
    )
    if code not in (0, 1):  # grep exits 1 on no matches, >1 on error
        return None
    return len([line for line in out.splitlines() if line.strip()])


def snapshot() -> ScanSnapshot:
    """Take a metrics snapshot of the local repo, if available."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    if not s.repo_path:
        return ScanSnapshot(taken_at=now)
    repo = s.repo_path.rstrip("/")
    return ScanSnapshot(
        npm_vulns=_npm_vuln_count(repo),
        py_vulns=_py_vuln_count(repo),
        any_types=_grep_count(repo, r":\s*any\b|\bas any\b", "superset-frontend/src"),
        sqla_legacy=None,
        taken_at=now,
    )
