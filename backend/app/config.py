"""Application configuration, loaded from environment variables."""

import os
from functools import lru_cache


class Settings:
    """Runtime settings sourced from the environment.

    DEMO_MODE lets the whole system run end-to-end without a live Devin key,
    so the dashboard and orchestration flow are fully demoable offline.
    """

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
        # Force demo mode, or auto-enable it when no Devin key is present.
        self.demo_mode: bool = (
            os.environ.get("DEMO_MODE", "").lower() in {"1", "true", "yes"}
            or not self.devin_api_key
        )
        # How often the orchestrator polls Devin for session status (seconds).
        self.poll_interval: float = float(os.environ.get("POLL_INTERVAL", "10"))
        # Ceiling on remediation sessions started per run (cost guard).
        self.max_sessions_per_run: int = int(
            os.environ.get("MAX_SESSIONS_PER_RUN", "6")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
