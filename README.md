# Remediation Engineer — powered by Devin

A **Remediation Engineer** built on the [Devin API](https://docs.devin.ai/api-reference/overview)
that autonomously works down two streams of unglamorous engineering work in
[Apache Superset](https://github.com/apache/superset) that human teams
chronically under-serve:

| Vertical | What it tackles | Why it rots |
| --- | --- | --- |
| 🔴 **Vulnerabilities** (urgent) | CVE dependency upgrades | "We'll patch it next sprint" |
| 🔵 **Code-quality backlog** (toil) | SQLAlchemy 1.x → 2.0 migration | Never wins prioritization |

Both are mechanical, well-scoped, and high-volume — exactly the shape an
autonomous coding agent excels at, and exactly the shape a human team will always
deprioritize.

> 🎥 **[Watch the 5-minute walkthrough on Loom →](https://www.loom.com/share/ab1e263927b64be4a30cbc1506b6c404)**

### The two task types in detail

**🔴 CVE dependency upgrades.** Superset pins exact package versions in
`requirements/base.txt`, and some have published CVEs. `pip-audit` surfaces the
precise *package / version / CVE / fixed-version* triplet — e.g. **Pillow 9.3.0 →
9.3.1 (CVE-2023-44271)**. Each becomes a GitHub issue with an unambiguous
instruction: bump the version, run the suite, open a PR. This is the *ideal* Devin
task — zero judgment, verifiable output, and a narrative that lands instantly with
a security-conscious VP: **automatic CVE remediation with no engineer in the loop.**

**🔵 SQLAlchemy legacy `.query()` migration.** Superset was built on SQLAlchemy
1.x, whose session-based `.query()` API is deprecated in 2.0 and slated for
removal. A grep surfaces modules still using the old pattern; each becomes an issue
asking Devin to rewrite the ORM calls to the modern `select()` style. It's a
forward-compatibility refactor (not a version bump) — equally well-scoped and
repeatable, and it shows Devin handling **real code refactoring**, a stronger
technical demo than dependency bumps alone.

> **Why only one of each?** The default config scopes a run to exactly two issues
> (one CVE upgrade + one SQLAlchemy migration) **purely for cost / Devin usage-limit
> reasons** — each issue spawns its own Devin session, and ACUs are metered. This
> is a demo-budget choice, **not** a capability limit: the system is built to fan
> out across as many issues as discovery finds. Flip the guards off
> (`FOCUSED_MODE=false`, `FINDINGS_PER_VERTICAL=0`, `FAST_MODE=false`) for broad,
> open-ended discovery (npm + pip vulns, `any`-type cleanup, etc.) at full scale.
>
> The relevant cost controls: `FINDINGS_PER_VERTICAL` (issues per vertical),
> `MAX_SESSIONS_PER_RUN` (concurrent fix sessions), and `MAX_ACU_LIMIT`
> (hard per-session ACU ceiling).

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

The dashboard answers in real time:

- **Fixing sessions in progress** — how many fix sessions are actively working
- **PRs opened** — pull requests created across runs
- **Succeeded** — fixes that **passed their tests and are ready to merge**
- **Success rate** — succeeded ÷ (succeeded + failed)
- **Vulnerabilities fixed** — before/after `pip-audit` delta (needs a mounted checkout)
- **Code-quality issues fixed** — count of succeeded code-quality fix sessions

## Why Devin (and not a script)

A `dependabot`/codemod can bump a version or run a regex. It **cannot** read a
breaking changelog, adapt the call sites, run the test suite, and decide whether
the result is safe to merge. The Remediation Engineer leans on Devin for exactly
that *judgment* — which is why a naive `audit fix` would brick the breaking
upgrades this handles cleanly.

---

## Architecture

- **Backend** — FastAPI. `orchestrator.py` is the state machine; `devin_client.py`
  wraps the Devin **v3** Organization API; `scanner.py` produces deterministic
  before/after metrics; `store.py` tracks runs.
- **Frontend** — Next.js (App Router) single-pane control room.

### Devin v3 API surface used
| Call | Endpoint |
| --- | --- |
| Verify key | `GET /v3/self` |
| Create session | `POST /v3/organizations/{org}/sessions` |
| Poll status | `GET /v3/organizations/{org}/sessions/{id}` |
| Read messages | `GET /v3/organizations/{org}/sessions/{id}/messages` |
| Stop session | `POST /v3/organizations/{org}/sessions/{id}/archive` |
| Create schedule | `POST /v3/organizations/{org}/schedules` |

### Configuration flags (env vars)
| Flag | Default | Effect |
| --- | --- | --- |
| `FOCUSED_MODE` | `true` | Restrict to CVE upgrades + SQLAlchemy migration (vs. open-ended) |
| `FINDINGS_PER_VERTICAL` | `1` | Max findings per vertical (`0` = unlimited, ~6 total) |
| `FAST_MODE` | `true` | Quick, time-boxed investigation — no repo exploration, skip the slow full test suite, minimal change |
| `MAX_ACU_LIMIT` | `10` | Hard per-session ACU spend ceiling (`0` = no cap) |
| `MAX_SESSIONS_PER_RUN` | `6` | Cap on concurrent fix sessions per run |
| `SCHEDULE_CRON` / `SCHEDULE_TIMEZONE` | `0 9 * * *` / `America/Los_Angeles` | Daily schedule timing |
| `REPO_PATH` | `/superset` | Container path to the Superset checkout (mounted from `../superset_armando`) for before/after scan metrics |

---

## Quick start

### The two repositories

This project spans **two repos**:

| Repo | Role |
| --- | --- |
| **`devin-automation-project`** (this one) | The automation — orchestrator, dashboard, Devin integration |
| **[`superset_armando`](https://github.com/ArmandoABD/superset_armando)** | The Apache Superset fork it operates on — receives the **issues + PRs** Devin creates |

For the before/after scan metrics, `docker-compose.yml` mounts the fork as a
sibling directory, so clone them **side by side**:

```bash
git clone https://github.com/ArmandoABD/devin-automation-project.git
git clone https://github.com/ArmandoABD/superset_armando.git
# parent/
# ├── devin-automation-project/   ← run docker compose here
# └── superset_armando/           ← mounted into the backend for scan metrics
```

> If you only clone this repo, everything still works — Devin's sessions, the
> issues/PRs, and all dashboard metrics run via the live API + GitHub. Only the
> local before/after vulnerability-count delta is skipped (it needs the fork on
> disk). Adjust the mount in `docker-compose.yml` if your fork lives elsewhere.

### Option A — Docker (recommended)

```bash
cp .env.example .env        # add DEVIN_API_KEY + DEVIN_ORG_ID + GITHUB_TOKEN
docker compose up --build
```

- Dashboard → http://localhost:3000
- API docs → http://localhost:8000/docs

Add your Devin v3 service-user key and org ID to `.env` (see **Going live**
below), then click **Run remediation** to dispatch Devin against the live repo.
Verify your key first with `curl localhost:8000/api/verify-credentials`.

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
3. Before/after scan metrics work out of the box: `docker-compose.yml` mounts
   `../superset_armando` → `/superset` (read-only) with `REPO_PATH=/superset`.
   Adjust the mount if your fork lives elsewhere.
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

**Proof of impact (before/after).** With the Superset checkout mounted at
`REPO_PATH`, the engineer runs `pip-audit` against `requirements/base.txt` at the
start of a run and again on demand via the **Re-scan** button — so once a CVE fix
lands you can watch the vulnerability count drop (e.g. `7 → 6`). The fix lives on
a PR branch, so the count moves after the change reaches the local checkout
(merge + pull, or apply the branch locally). Without the mount, the
session/PR/success metrics still work; only the before/after delta is skipped.
(Python CVEs use `pip-audit` inside the container; npm auditing needs Node and is
not run in the backend image.)

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
