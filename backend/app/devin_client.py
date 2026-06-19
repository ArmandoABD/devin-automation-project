"""Async HTTP client for the Devin v3 Organization API."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from .config import get_settings

# v3 session state machine. The real v3 payload exposes a top-level `status`
# plus a finer `status_detail` (e.g. "waiting_for_user" when Devin has finished
# its work or needs input). We derive a single internal state from both.
_FINISHED_STATUS = {"exit", "finished", "completed", "stopped"}
_FAILED_STATUS = {"error", "failed"}
# status_detail values that mean "Devin has stopped working and is idle/waiting"
_IDLE_DETAILS = {"waiting_for_user", "blocked", "suspended", "finished"}
# states the orchestrator stops polling on
_TERMINAL = {"finished", "failed", "blocked", "expired"}

_PR_RE = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/pull/\d+")
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class DevinClient:
    def __init__(self) -> None:
        s = get_settings()
        self._base = s.devin_base_url.rstrip("/")
        self._org = s.devin_org_id
        self._headers = {
            "Authorization": f"Bearer {s.devin_api_key}",
            "Content-Type": "application/json",
        }

    def _sessions_url(self) -> str:
        return f"{self._base}/organizations/{self._org}/sessions"

    async def verify(self) -> dict[str, Any]:
        """GET /v3/self — confirms the key works and returns the principal."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self._base}/self", headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    async def create_session(
        self,
        prompt: str,
        *,
        title: Optional[str] = None,
        tags: Optional[list[str]] = None,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        """Create a session; returns {session_id, url, status}."""
        body: dict[str, Any] = {"prompt": prompt}
        if title:
            body["title"] = title
        if tags:
            body["tags"] = tags
        if idempotent:
            body["idempotent"] = idempotent

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                self._sessions_url(), headers=self._headers, json=body
            )
            resp.raise_for_status()
            return resp.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{self._sessions_url()}/{session_id}", headers=self._headers
            )
            resp.raise_for_status()
            return resp.json()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{self._sessions_url()}/{session_id}/messages",
                headers=self._headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", data) if isinstance(data, dict) else data

    async def send_message(self, session_id: str, message: str) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._sessions_url()}/{session_id}/messages",
                headers=self._headers,
                json={"message": message},
            )
            resp.raise_for_status()

    async def archive_session(self, session_id: str) -> None:
        """Archive a session, putting it to sleep if running (stops ACU burn)."""
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._sessions_url()}/{session_id}/archive",
                headers=self._headers,
            )
            resp.raise_for_status()

    # --- schedules (recurring sessions) -------------------------------------

    def _schedules_url(self) -> str:
        return f"{self._base}/organizations/{self._org}/schedules"

    async def create_schedule(
        self, *, name: str, prompt: str, cron_schedule: str, timezone: str
    ) -> dict[str, Any]:
        """Create a recurring scheduled session (v3 Schedules API).

        The v3 API takes the cron string in the `frequency` field.
        """
        body = {
            "name": name,
            "prompt": prompt,
            "frequency": cron_schedule,
            "timezone": timezone,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                self._schedules_url(), headers=self._headers, json=body
            )
            resp.raise_for_status()
            return resp.json()

    async def list_schedules(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(self._schedules_url(), headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", data) if isinstance(data, dict) else data

    async def delete_schedule(self, schedule_id: str) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.delete(
                f"{self._schedules_url()}/{schedule_id}", headers=self._headers
            )
            resp.raise_for_status()

    @staticmethod
    def session_state(payload: dict[str, Any]) -> str:
        """Derive internal state from v3 `status` + `status_detail`."""
        status = (payload.get("status") or payload.get("status_enum") or "").lower()
        detail = (payload.get("status_detail") or "").lower()
        if status in _FAILED_STATUS:
            return "failed"
        if status in _FINISHED_STATUS:
            return "finished"
        if detail in _IDLE_DETAILS or status in {"suspended", "blocked"}:
            return "blocked"
        return "working"

    @classmethod
    def is_terminal(cls, payload_or_state: Any) -> bool:
        state = (
            payload_or_state
            if isinstance(payload_or_state, str)
            else cls.session_state(payload_or_state)
        )
        return state in _TERMINAL

    @staticmethod
    def extract_structured(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Return structured output from the session payload if present."""
        for key in ("structured_output", "structured_output_result", "output"):
            val = payload.get(key)
            if isinstance(val, dict):
                return val
        return None

    @classmethod
    def extract_pr_url(cls, payload: dict[str, Any], blob: str = "") -> Optional[str]:
        # v3 returns `pull_requests` (plural list); older shapes used singular.
        prs = payload.get("pull_requests")
        if isinstance(prs, list):
            for pr in prs:
                url = pr.get("url") if isinstance(pr, dict) else pr
                if url:
                    return url
        pr = payload.get("pull_request")
        if isinstance(pr, dict) and pr.get("url"):
            return pr["url"]
        match = _PR_RE.search(blob or json.dumps(payload))
        return match.group(0) if match else None

    @classmethod
    def extract_json_from_text(cls, blob: str) -> Optional[dict[str, Any]]:
        """Find the last fenced JSON object in a text blob (fallback parser)."""
        matches = _JSON_BLOCK_RE.findall(blob or "")
        for raw in reversed(matches):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                continue
        return None
