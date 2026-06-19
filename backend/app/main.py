"""FastAPI app: event-driven orchestration and observability API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import scanner
from .config import get_settings
from .devin_client import DevinClient
from .models import CreateRunRequest, Metrics, Run
from .orchestrator import create_run, stop_run
from .store import store

app = FastAPI(title="Devin Remediation Orchestrator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "demo_mode": s.demo_mode,
        "devin_base_url": s.devin_base_url,
        "github_repo": s.github_repo,
        "repo_scanning": bool(s.repo_path),
    }


@app.get("/api/verify-credentials")
async def verify_credentials() -> dict:
    """Confirm the Devin key works (GET /v3/self). No-op in demo mode."""
    s = get_settings()
    if s.demo_mode:
        return {"demo_mode": True, "verified": False}
    try:
        principal = await DevinClient().verify()
        return {"demo_mode": False, "verified": True, "principal": principal}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/runs", response_model=Run)
async def trigger_run(req: CreateRunRequest) -> Run:
    """THE EVENT TRIGGER: kicks off discovery + remediation for a vertical."""
    return create_run(req.vertical)


@app.get("/api/runs", response_model=list[Run])
async def list_runs() -> list[Run]:
    return store.list()


@app.get("/api/runs/{run_id}", response_model=Run)
async def get_run(run_id: str) -> Run:
    run = store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/runs/{run_id}/stop", response_model=Run)
async def stop(run_id: str) -> Run:
    """Stop a run: cancel orchestration and archive its live Devin sessions."""
    run = await stop_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/runs/{run_id}/verify", response_model=Run)
async def verify_impact(run_id: str) -> Run:
    """Re-scan to capture the post-merge impact delta (before/after proof)."""
    run = store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    run.after = scanner.snapshot()
    store.save(run)
    return run


@app.get("/api/metrics", response_model=Metrics)
async def metrics() -> Metrics:
    return store.metrics()


@app.post("/api/webhook")
async def webhook(payload: dict) -> dict:
    """Alternate trigger: a scan/CI/issue webhook fires a run.

    Accepts an optional {"vertical": "security|backlog|both"} body so a real
    scanner (e.g. a nightly pip-audit job) can hand work off to Devin.
    """
    from .models import Vertical

    vertical = Vertical(payload.get("vertical", "both"))
    run = create_run(vertical)
    return {"triggered": True, "run_id": run.id}
