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

Cap the total at a reasonable number (max ~6) so we get a clean demo.

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
     affected tests) and confirm they pass.
  4. Open a pull request against {repo} that closes the issue. Reference the
     issue in the PR body.

IMPORTANT: end your final message with a single fenced ```json block containing
{{"pr_url": "...", "tests_pass": true/false, "summary": "one-line description of
what you changed"}}. This block is parsed programmatically."""
