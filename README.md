# Devin Remediation Control

**Event-driven autonomous remediation for [Apache Superset](https://github.com/apache/superset), powered by the [Devin API](https://docs.devin.ai/api-reference/overview).**

A trigger fires → Devin **discovers** concrete engineering issues and files GitHub
issues → Devin **remediates** each one in its own session and opens a PR → a live
dashboard reports **what happened and whether it worked.**

---

## The problem

Every mature codebase carries two kinds of unglamorous work that humans
chronically under-serve:

| Vertical | Nature | Example in Superset | Why it rots |
| --- | --- | --- | --- |
| 🔴 **Security** (urgent) | Fix before it bites | `flask`, `pyjwt`, `paramiko` CVEs (11 found via `pip-audit`) | "We'll patch it next sprint" |
| 🔵 **Backlog** (toil) | Trivial × thousands | 1,139 `any` types, 533 legacy `.query()` calls | Never wins prioritization |

Both are **mechanical, well-scoped, and high-volume** — the exact shape an
autonomous coding agent eats for breakfast, and the exact shape a human team
will always deprioritize. This system turns each finding into an autonomous PR.

## Why Devin (and not a script)

A `dependabot`/codemod can bump a version or run a regex. It **cannot** read a
breaking changelog, adapt call sites, run the test suite, and back out if it
fails. Devin does the *judgment* part — which is why ~30% of `npm audit` fixes
here need breaking upgrades that a dumb `audit fix` would brick.

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

With an empty `.env`, it boots in **DEMO_MODE** — click **Run Remediation** and
watch the full discovery → fix → PR → impact lifecycle play out.

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

---

## Observability — "how would a leader know this is working?"

The dashboard answers exactly that:

- **Throughput** — PRs opened, findings discovered, sessions started.
- **Success / failure** — per-session test pass/fail; aggregate success rate.
- **Progress** — live status dots (pending → working → finished) per session.
- **Proof of impact** — before/after vulnerability + `any`-type counts, refreshed
  by the **Re-scan** button after PRs merge (`32 vulns → 29`).

Every number is a real endpoint: `GET /api/metrics`, `GET /api/runs`.

---

## Next steps (real customer engagement)

- Swap the button for a **native v3 Schedule** (nightly backlog drain) + a
  **scan webhook** (instant CVE response) — both already call `create_run()`.
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
