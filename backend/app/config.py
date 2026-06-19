"""Application configuration, loaded from environment variables."""

import os
from functools import lru_cache


class Settings:
    """Runtime settings sourced from the environment."""

    def __init__(self) -> None:
        # v3 service-user key (cog_ prefix). v1/v2 keys (apk_*) also work if the
        # base URL is pointed at the legacy host.
        self.devin_api_key: str = os.environ.get("DEVIN_API_KEY", "")
        self.devin_base_url: str = os.environ.get(
            "DEVIN_BASE_URL", "https://api.devin.ai/v3"
        )
        # Organization ID for v3 org-scoped routes (Settings > Service Users).
        self.devin_org_id: str = os.environ.get("DEVIN_ORG_ID", "")
        self.github_token: str = os.environ.get("GITHUB_TOKEN", "")
        # owner/repo of the Superset fork that receives issues + PRs
        self.github_repo: str = os.environ.get(
            "GITHUB_REPO", "ArmandoABD/superset_armando"
        )
        # Path to a local checkout of the fork, used by the scanner for
        # deterministic before/after metrics. Optional.
        self.repo_path: str = os.environ.get("REPO_PATH", "")
        # Whether a Devin API key is configured. Without it the system can't
        # create sessions and the API surfaces a clear error.
        self.has_devin_key: bool = bool(self.devin_api_key)
        # How often the orchestrator polls Devin for session status (seconds).
        self.poll_interval: float = float(os.environ.get("POLL_INTERVAL", "10"))
        # Ceiling on remediation sessions started per run (cost guard).
        self.max_sessions_per_run: int = int(
            os.environ.get("MAX_SESSIONS_PER_RUN", "6")
        )
        # Demo cap: max findings per vertical (0 = unlimited / ~6 total).
        # Set to 1 to keep a demo run small: one CVE + one code-quality fix.
        self.findings_per_vertical: int = int(
            os.environ.get("FINDINGS_PER_VERTICAL", "0")
        )
        # Focused mode: narrow each vertical to one predictable task type —
        # CVE dependency upgrades (security) and SQLAlchemy .query()->select()
        # migration (code quality). Off = broader, open-ended discovery.
        self.focused_mode: bool = os.environ.get("FOCUSED_MODE", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        # Fast mode: time-box Devin to a quick investigation — no repo
        # exploration, skip the slow full test suite, minimal change. Trades
        # thoroughness for speed; ideal for a live demo.
        self.fast_mode: bool = os.environ.get("FAST_MODE", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        # Hard per-session ACU spend ceiling (0 = no cap). Devin stops the
        # session when it hits this, so cost can never run away.
        self.max_acu_limit: int = int(os.environ.get("MAX_ACU_LIMIT", "0"))
        # Native Devin schedule: daily cron + timezone for the recurring run.
        self.schedule_cron: str = os.environ.get("SCHEDULE_CRON", "0 9 * * *")
        self.schedule_timezone: str = os.environ.get(
            "SCHEDULE_TIMEZONE", "America/Los_Angeles"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
