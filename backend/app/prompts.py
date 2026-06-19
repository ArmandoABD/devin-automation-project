"""Prompt builders and structured-output schemas for Devin sessions."""

from __future__ import annotations

from typing import Any

from .config import get_settings
from .models import Vertical

DISCOVERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "vertical": {"type": "string", "enum": ["security", "backlog"]},
                    "severity": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"}},
                    "target": {"type": "string"},
                    "issue_url": {"type": "string"},
                },
                "required": ["vertical", "title", "target"],
            },
        }
    },
    "required": ["findings"],
}

REMEDIATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pr_url": {"type": "string"},
        "tests_pass": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["summary"],
}


def discovery_prompt(vertical: Vertical) -> str:
    s = get_settings()
    repo = s.github_repo

    if s.focused_mode:
        # Narrow each vertical to one predictable, well-understood task type.
        security_block = """
SECURITY VERTICAL — CVE dependency upgrades ONLY:
  - Run `pip-audit -r requirements/base.txt` to surface pinned Python packages
    with published CVEs (exact package / current version / CVE / fixed version).
  - Each finding = ONE package upgrade. The fix is unambiguous: bump to the
    fixed version, run the test suite, open a PR. No other change types.
  - severity = the advisory severity.
"""
        backlog_block = """
CODE-QUALITY VERTICAL — SQLAlchemy 1.x -> 2.0 migration ONLY:
  - Grep the Python codebase for legacy session-based `.query(` ORM calls
    (deprecated in SQLAlchemy 2.0).
  - Each finding = ONE module to migrate from `.query()` to the modern
    `select()` style. Pure refactor — behavior must stay identical. No other
    change types.
"""
    else:
        security_block = f"""
SECURITY VERTICAL (urgent — fix before it bites):
  - In the frontend dir, run `npm audit --json` and collect dependency
    vulnerabilities that HAVE a fix available (skip ones with no fix).
  - Run `pip-audit -r requirements/base.txt` and collect vulnerable Python
    packages with known fix versions (e.g. flask, pyjwt, paramiko).
  - One finding per package. severity = the advisory severity.
"""

        backlog_block = """
BACKLOG VERTICAL (toil — trivial but never prioritized):
  - Find directories under superset-frontend/src with `any` TypeScript types
    (`: any`, `as any`, `<any>`). One finding per top-level subdirectory.
  - Optionally find modules still using legacy SQLAlchemy `.query(` syntax that
    should move to the 2.0 `select()` style. One finding per module.
"""

    scope = ""
    if vertical in (Vertical.SECURITY, Vertical.BOTH):
        scope += security_block
    if vertical in (Vertical.BACKLOG, Vertical.BOTH):
        scope += backlog_block

    limit = s.findings_per_vertical
    if limit > 0:
        cap = (
            f"IMPORTANT: report EXACTLY {limit} finding(s) PER VERTICAL — pick "
            f"the highest-severity / highest-impact one(s) and ignore the rest. "
            f"This is a focused run; do not exceed the limit."
        )
    else:
        cap = "Cap the total at a reasonable number (max ~6) so we get a clean demo."

    return f"""You are an automated remediation scout for the repository {repo}.

Goal: discover concrete, independently-fixable engineering issues, then create a
GitHub issue in {repo} for each one.

{scope}
For EVERY finding:
  1. Check the repo's existing OPEN issues first. If an open issue already
     covers this finding (same package / same fix), REUSE its URL instead of
     creating a duplicate. Otherwise create a new GitHub issue in {repo} with a
     clear title, a body that includes the evidence (scanner output / file
     paths) and explicit ACCEPTANCE CRITERIA, and labels:
     ["devin", the vertical name, severity].
  2. Keep each finding small enough that a single PR can resolve it.

{cap}

IMPORTANT: end your final message with a single fenced ```json block containing
{{"findings": [...]}}, where each finding has: vertical, severity, title, body,
labels, target, and issue_url (the URL of the GitHub issue you created). This
block is parsed programmatically."""


def remediation_prompt(
    title: str, body: str, target: str, issue_url: str | None
) -> str:
    s = get_settings()
    repo = s.github_repo
    issue_ref = f"\nGitHub issue: {issue_url}" if issue_url else ""

    return f"""You are remediating a single engineering issue in {repo}.

Issue: {title}{issue_ref}
Target: {target}

Details / acceptance criteria:
{body or "Resolve the issue described above."}

Do the following:
  1. Create a branch and implement the fix.
  2. Make sure the change satisfies the acceptance criteria.
  3. Run the relevant checks (`pre-commit run` for touched files, plus any
     affected tests).
  4. Open a pull request against {repo} that closes the issue, referencing the
     issue in the PR body. Gate the PR state on the checks from step 3:
       - If ALL checks/tests pass -> open a normal, ready-for-review PR.
       - If any test FAILS, or you could not run the tests -> open the PR as a
         DRAFT and add the label `needs-human`, so it cannot be merged until a
         human reviews it. Never open a non-draft PR with failing tests.

IMPORTANT: end your final message with a single fenced ```json block containing
{{"pr_url": "...", "tests_pass": true/false, "is_draft": true/false, "summary":
"one-line description of what you changed"}}. This block is parsed
programmatically."""


def scheduled_remediation_prompt() -> str:
    """Self-contained prompt for the recurring scheduled run.

    Unlike on-demand runs (which the orchestrator fans out into one session per
    issue), a Devin Schedule fires a single session, so this prompt drives the
    whole loop — discover, file issues, fix, and open PRs — end to end.
    """
    s = get_settings()
    repo = s.github_repo
    return f"""You are the scheduled Remediation Engineer for {repo}. Run the
full remediation loop autonomously across BOTH verticals.

1. DISCOVER
   - Vulnerabilities: run `pip-audit -r requirements/base.txt` and
     `npm audit --json` (frontend); collect issues that HAVE a fix available.
   - Code-quality backlog: find a small, well-scoped cleanup (e.g. `any` types
     in one src subdirectory, or legacy SQLAlchemy `.query()` in one module).
   - Cap the total at ~6 findings for a clean run.

2. FILE ISSUES
   - For each finding, reuse an existing open GitHub issue if one already covers
     it; otherwise create one in {repo} with evidence, acceptance criteria, and
     labels ["devin", vertical, severity].

3. REMEDIATE
   - Fix each finding on its own branch and run the relevant checks
     (`pre-commit run` for touched files, plus affected tests).
   - Open a pull request that closes the issue. If tests pass, open it ready for
     review; if tests fail or could not run, open it as a DRAFT labelled
     `needs-human`. Never open a non-draft PR with failing tests.

End your final message with a fenced ```json block:
{{"prs": [{{"issue_url": "...", "pr_url": "...", "tests_pass": true/false,
"is_draft": true/false}}], "summary": "what this run accomplished"}}."""
