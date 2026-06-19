# Remediation Engineer — powered by Devin

A **Remediation Engineer** built on the [Devin API](https://docs.devin.ai/api-reference/overview)
that autonomously works down two streams of unglamorous engineering work in
[Apache Superset](https://github.com/apache/superset) that human teams
chronically under-serve:

| Vertical | What it tackles | Why it rots |
| --- | --- | --- |
| 🔴 **Vulnerabilities** (urgent) | Dependency CVEs surfaced by `pip-audit` / `npm audit` (e.g. `flask`, `pyjwt`, `paramiko`) | "We'll patch it next sprint" |
| 🔵 **Code-quality backlog** (toil) | Trivial-but-endless cleanup — `any` types, legacy SQLAlchemy `.query()`, etc. | Never wins prioritization |

Both are mechanical, well-scoped, and high-volume — exactly the shape an
autonomous coding agent excels at, and exactly the shape a human team will always
deprioritize.

## How it runs

The Remediation Engineer can be **scheduled** or **run on demand**:

- **Scheduled** — a recurring daily run at **9 AM** (America/Los_Angeles),
  created through **Devin's native v3 Schedules API**. The schedule fires a Devin
  session that runs the full remediation loop end to end. Managed via the
  `/api/schedule` endpoints (create / list / delete).
- **On demand** — a full, observable lifecycle from the dashboard: **start** a
  Devin session with one click, **watch** it work live, **stop** it instantly at
  any point (halts the session and its spend), and **see when it finishes**.

## What the Remediation Engineer does

Each run is a two-phase pipeline:

1. **Discovery** — a single Devin session scans the repo for problems in the
   selected vertical(s), then **creates a GitHub issue** for each finding (title,
   evidence, acceptance criteria, labels). The discovery session returns the list
   of findings.
2. **Remediation** — the engineer **spins out one Devin session per issue**, all
   running concurrently. Each session implements the fix on its own branch and
   **opens a pull request** that closes its issue when merged.

```
trigger ─► Discovery session ─► creates GitHub issues ─► findings
                                                            │
                                  one fix session per issue ▼
                                  ───────────────────────────► Pull Requests
                                  (each closes its issue on merge)
```

The **output is pull requests** — concrete, reviewable code changes that, once
merged, resolve the issues. Failing/unverified fixes are opened as **draft** PRs
(labelled `needs-human`) so they can never be merged by accident; passing fixes
are opened ready-for-review.

## What the reporting shows

The dashboard answers *"how would an engineering leader know this is working?"*
in real time:

- **Sessions in progress** — how many Devin agents are actively working right now
- **PRs opened** — pull requests created across runs
- **Succeeded** — fixes that **passed their tests and are ready to merge**
- **Success rate** — succeeded ÷ (succeeded + failed)
- **Vulnerabilities fixed** & **Code-quality issues fixed** — the realized impact,
  which lands as the PRs are reviewed and merged

## Why Devin (and not a script)

A `dependabot`/codemod can bump a version or run a regex. It **cannot** read a
breaking changelog, adapt the call sites, run the test suite, and decide whether
the result is safe to merge. The Remediation Engineer leans on Devin for exactly
that *judgment* — which is why a naive `audit fix` would brick the breaking
upgrades this handles cleanly.

---

## Architecture

```
                         ┌─────────────────────── EVENT TRIGGERS ───────────────────────┐
                         │  Dashboard button   ·   POST /api/webhook   ·   v3 Schedule   │
                         └───────────────────────────────┬──────────────────────────────┘
                                                          ▼
   ┌──────────────────────────── FastAPI orchestrator (backend/) ────────────────────────────┐
   │  1. snapshot()  ── pip-audit / npm audit  ──►  BEFORE metrics                             │
   │  2. DISCOVERY   ── Devin session ──►  scans repo, files GitHub issues, returns findings   │
   │  3. REMEDIATION ── one Devin session per finding (concurrent) ──►  opens a PR each        │
   │  4. snapshot()  ── re-scan  ──►  AFTER metrics  (before/after = proof of impact)          │
   └───────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                ▼
   Next.js dashboard (frontend/)  ── polls /api/runs + /api/metrics ──►  live status, PRs, KPIs
                                                │
                         GitHub fork (ArmandoABD/superset_armando) ◄── issues + PRs land here
```

- **Backend** — FastAPI. `orchestrator.py` is the state machine; `devin_client.py`
  wraps the Devin **v3** Organization API; `scanner.py` produces deterministic
  before/after metrics; `store.py` tracks runs.
- **Frontend** — Next.js (App Router) single-pane control room.
- **DEMO_MODE** — with no Devin key, the full lifecycle is **simulated** with the
  real findings from the Superset scan, so the demo runs offline and
  deterministically. Drop in a `cog_` key to go live.

### Devin v3 API surface used
| Call | Endpoint |
| --- | --- |
| Verify key | `GET /v3/self` |
| Create session | `POST /v3/organizations/{org}/sessions` |
| Poll status | `GET /v3/organizations/{org}/sessions/{id}` |
| Read messages | `GET /v3/organizations/{org}/sessions/{id}/messages` |

---

## Quick start

### Option A — Docker (recommended)

```bash
cp .env.example .env        # optional: add DEVIN_API_KEY + DEVIN_ORG_ID for LIVE mode
docker compose up --build
```

- Dashboard → http://localhost:3000
- API docs → http://localhost:8000/docs

With an empty `.env`, it boots in **DEMO_MODE** — click **Run remediation** and
watch the full discovery → fix → PR → impact lifecycle play out with realistic
simulated data (no key or network needed).

### Option B — local dev

```bash
# backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (new shell)
cd frontend && npm install && npm run dev
```

---

## Going live with Devin

1. Create a service user → copy its `cog_` key and org ID (Settings → Service Users).
2. Put them in `.env`:
   ```env
   DEVIN_API_KEY=cog_...
   DEVIN_ORG_ID=...
   GITHUB_TOKEN=ghp_...        # PAT with repo scope on the fork
   GITHUB_REPO=ArmandoABD/superset_armando
   ```
3. (Optional) enable real before/after scans by mounting a local Superset
   checkout — uncomment the `volumes:` block in `docker-compose.yml` and set
   `REPO_PATH=/superset`.
4. `docker compose up --build` → the badge flips to **LIVE · Devin v3**.

Verify the key end-to-end: `curl localhost:8000/api/verify-credentials`.

### Enable the daily schedule

Create the recurring 9 AM (America/Los_Angeles) run via Devin's Schedules API:

```bash
curl -X POST localhost:8000/api/schedule   # idempotent — won't duplicate
curl localhost:8000/api/schedule           # list / inspect
```

Override timing with `SCHEDULE_CRON` / `SCHEDULE_TIMEZONE` in `.env`. Delete with
`curl -X DELETE localhost:8000/api/schedule/<scheduled_session_id>`.

---

## Observability internals

Every number on the dashboard is backed by a real endpoint — `GET /api/metrics`
and `GET /api/runs` — which the frontend polls every few seconds. Each run card
also exposes per-session status dots (pending → working → finished), the linked
Devin session, and the resulting PR.

**Proof of impact (before/after).** When a local Superset checkout is mounted
(`REPO_PATH`), the engineer takes a `pip-audit`/`npm audit` snapshot at the start
of a run and again on demand via the **Re-scan** button — so once PRs merge you
can watch the vulnerability count drop (`32 → 29`). Without the mount, the
session/PR/success metrics still work; only the before/after delta is skipped.

---

## Next steps (real customer engagement)

- Add a **scan webhook** (e.g. Dependabot alert → instant CVE response) alongside
  the existing daily schedule + on-demand triggers.
- Devin **Playbooks / Knowledge notes** to encode repo conventions (the Superset
  `CLAUDE.md` rules) so PRs match house style on the first try.
- Gate auto-merge on CI green + human approval for the security vertical.
- Persist runs to Postgres and ship the metrics to Datadog/Grafana.

---

## Project layout

```
devin-automation-project/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   └── app/
│       ├── main.py           # FastAPI routes (triggers + observability)
│       ├── orchestrator.py   # discovery → remediation state machine
│       ├── devin_client.py   # Devin v3 API client
│       ├── scanner.py        # npm audit / pip-audit before-after metrics
│       ├── prompts.py        # discovery + remediation prompts
│       ├── store.py          # run tracking + metrics aggregation
│       └── models.py         # pydantic schemas
└── frontend/
    ├── Dockerfile
    ├── app/page.tsx          # the control-room dashboard
    └── lib/api.ts            # typed API client
```
