# Devin API Reference — A Builder's Guide

> **Audience:** an engineer or agent who wants to build an application on top of the
> Devin API. This is a distilled, opinionated map of the surface area you actually
> need, with exact request/response schemas, the session lifecycle state machine,
> and the canonical "drive a session to completion" recipe.
>
> **Source of truth:** [docs.devin.ai/api-reference](https://docs.devin.ai/api-reference/overview).
> The machine-readable index lives at [docs.devin.ai/llms.txt](https://docs.devin.ai/llms.txt).
> When this doc and the live docs disagree, the live docs win — re-fetch the
> relevant `*.md` page (every doc page has a `.md` twin) before relying on a field.
>
> **Scope note:** schemas below were transcribed from the v3 reference pages. Where
> a page omitted an example or a field's exact constraints, that is flagged inline
> with _(not documented)_. Don't invent fields the API didn't promise.

---

## 0. TL;DR — the 30-second model

- **Use v3.** `v1` and `v2` still respond but are legacy. Everything new is under
  `https://api.devin.ai/v3`.
- **Two scopes:** organization (`/v3/organizations/{org_id}/…`) for day-to-day work
  (sessions, knowledge, playbooks, secrets, schedules) and enterprise
  (`/v3/enterprise/…`) for cross-org admin, billing, and metrics.
- **Auth is a bearer token** that starts with `cog_` (a *service user* key). One
  header on every request: `Authorization: Bearer cog_…`.
- **The primitive is a Session.** You `POST` a `prompt`, get a `session_id`, then
  **poll** the session until it reaches a terminal status. Sessions are
  asynchronous and long-running — there is no synchronous "run and return" call.
- **For programmatic results, request `structured_output`.** Give a JSON Schema at
  creation; read the validated object back off the session when it finishes.

---

## 1. Versions

| Version | Status | Notes |
| --- | --- | --- |
| **v3** | **Current** | Org + enterprise scopes, RBAC, cursor pagination, structured output. Build here. |
| v2 | Legacy | Enterprise management (members, orgs, consumption). Superseded by v3 `/enterprise`. |
| v1 | Legacy | Original sessions/knowledge/playbooks/secrets. Superseded by v3. |

A [migration guide](https://docs.devin.ai/api-reference/getting-started/migration-guide)
exists for moving v1/v2 → v3. New code should never start on v1/v2.

---

## 2. Hosts & base URLs

| Scope | Base URL |
| --- | --- |
| Organization | `https://api.devin.ai/v3/organizations/{org_id}` |
| Enterprise | `https://api.devin.ai/v3/enterprise` |
| Account-level | `https://api.devin.ai/v3/self` |

**Enterprise / self-hosted customers** may be issued a custom domain, e.g.
`https://api.your-company.devinenterprise.com`. Always make the base URL a config
value (this repo uses `DEVIN_BASE_URL`, defaulting to `https://api.devin.ai/v3`) —
never hardcode the host.

> Note on enterprise paths: some enterprise endpoints embed an org id, e.g.
> `/v3/enterprise/organizations/{org_id}/…`, yet still require *enterprise*
> permissions. Don't assume "has org_id in path ⇒ org-scoped token is enough."

---

## 3. Authentication

### 3.1 The header

Every request carries a bearer token:

```http
Authorization: Bearer cog_your_token_here
Content-Type: application/json
```

### 3.2 Token types

| Type | Prefix | Use it for | How to get it |
| --- | --- | --- | --- |
| **Service user key** (recommended) | `cog_` | Automation, CI/CD, backend services. RBAC-scoped, non-human identity. | Settings → **Service Users** → *Create service user* → *Generate API key*. **Shown once.** |
| Personal access token (PAT) | `cog_` | A human acting under their own identity. | **Closed beta**, feature-flagged. Email `support@cognition.ai`. Not available on SSO/enterprise accounts. |
| Legacy personal key | `apk_user_` | v1/v2 only. | Deprecated — no RBAC, no new features. |
| Legacy service key | `apk_` | v1 only. | Deprecated. |

**Build with a service user key (`cog_`).** It is the only first-class, RBAC-aware
credential for backends.

### 3.3 The two values you always need

```bash
export DEVIN_API_KEY="cog_…"     # the service user key
export DEVIN_ORG_ID="org-…"      # from Settings → Service Users
```

Both are required for org-scoped routes. The org id is prefixed `org-`.

### 3.4 Verify a credential — `GET /v3/self`

Your app's healthcheck / "is this key live" probe. Requires `ReadAccountMeta`.

```bash
curl https://api.devin.ai/v3/self -H "Authorization: Bearer $DEVIN_API_KEY"
```

Returns one of four **principal** shapes (discriminated by `principal_type`):

| `principal_type` | Key fields |
| --- | --- |
| `ServiceUserSelf` | `service_user_id`, `service_user_name`, `org_id?` |
| `PatUserSelf` | `user_id`, `user_name`, `api_key_id`, `api_key_name`, `org_id?` |
| `DevinBrainUserSelf` | `devin_id`, `org_id`, `user_id`, `creator_service_user_id?` |
| `WindsurfSessionUserSelf` | `user_id`, `org_id`, `user_name?` |

A `200` with a `ServiceUserSelf` body confirms the key works; a `401` means it
doesn't.

### 3.5 Permission model

v3 uses **per-endpoint, granular permissions** (not blanket roles). Each reference
page names the permission it needs. Permissions you'll touch most when building an
app:

| Permission | Gates |
| --- | --- |
| `ReadAccountMeta` | `GET /v3/self` |
| `ViewOrgSessions` | List / read sessions and messages |
| `ManageOrgSessions` | Send messages to a session |
| `UseDevinSessions` | Upload attachments |
| `ImpersonateOrgSessions` | Create sessions `create_as_user_id` |
| `ManageAccountKnowledge` | Knowledge notes CRUD |
| `ManageAccountPlaybooks` | Playbooks CRUD |
| `ManageOrgSecrets` | Secrets CRUD |

Org service users are scoped to one org. Enterprise service users authenticate at
`/v3/enterprise/*`, can operate across all orgs, and **inherit the org-level
permissions everywhere.** Give your service user the *minimum* role: **Member**
covers creating/managing sessions and resources; **Admin** is only needed for
settings and impersonation.

---

## 4. Conventions

### 4.1 Identifiers (prefixes are meaningful)

| Entity | Prefix | Example |
| --- | --- | --- |
| Organization | `org-` | `org-abc123def456` |
| Session ("devin id") | `devin-` | `devin-abc123def456` |
| Service user key | `cog_` | `cog_…` |

The session path parameter is literally named `devin_id` and carries the
`devin-…` value.

### 4.2 Timestamps

All timestamps are **Unix epoch integers** (e.g. `created_at`, `updated_at`).
`scheduled_at` (one-time schedules) is the exception: **ISO 8601** datetime.

### 4.3 Pagination (cursor-based)

List endpoints are cursor-paginated — **not** offset/limit (cursors survive
inserts/deletes mid-iteration).

**Request params:**
- `first` (int) — page size. Defaults vary; session-scoped lists allow **1–200, default 100**.
- `after` (string) — opaque cursor from the previous page. Omit for page 1.

**Response envelope** (`PaginatedResponse[T]`):

```jsonc
{
  "items": [ /* T[] */ ],
  "has_next_page": true,
  "end_cursor": "eyJsYXN0X2lkIjoiYWJjMTIzIn0=",
  "total": 142            // optional; may be null
}
```

**Iterate:**

```python
cursor = None
while True:
    page = get(url, params={"first": 100, **({"after": cursor} if cursor else {})})
    yield from page["items"]
    if not page["has_next_page"]:
        break
    cursor = page["end_cursor"]
```

### 4.4 Errors

Standard HTTP semantics:

| Code | Meaning | Typical cause |
| --- | --- | --- |
| `401` | Unauthenticated | Missing/invalid/expired `cog_` key |
| `403` | Forbidden | Key valid but lacks the required permission |
| `404` | Not found | Wrong `org_id`/`devin_id`, or no access |
| `422` | Validation error | Malformed body — see below |
| `429` | Rate limited | Back off and retry |

`422` returns an `HTTPValidationError`:

```jsonc
{ "detail": [ { "loc": ["body", "prompt"], "msg": "field required", "type": "value_error.missing" } ] }
```

> Specific rate-limit thresholds are **not published**. Treat `429` as a signal:
> exponential backoff + jitter, honor `Retry-After` if present.

---

## 5. Sessions — the core resource

A session is one autonomous Devin run: you give it a prompt (and optional context —
repos, knowledge, playbooks, secrets, a structured-output contract), Devin works
asynchronously, and you observe it via polling.

### 5.1 Create a session — `POST /v3/organizations/{org_id}/sessions`

**Request body** (`prompt` is the only required field):

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `prompt` | string | — | **Required.** The task. |
| `title` | string | — | Human label for the session. |
| `tags` | string[] | — | Free-form labels (filterable later). |
| `repos` | string[] | — | Repositories to work in. |
| `knowledge_ids` | string[] | — | Knowledge notes to attach. |
| `playbook_id` | string | — | Playbook to run. |
| `child_playbook_id` | string | — | Child playbook. |
| `secret_ids` | string[] | — | Pre-stored secrets to expose. |
| `session_secrets` | SessionSecretInput[] | — | Inline key/value secrets for this session. |
| `attachment_urls` | uri[] | — | Attachment URLs (≤2083 chars each); see §8. |
| `session_links` | string[] | — | Related sessions. |
| `devin_mode` | enum | org setting | `normal` \| `fast` \| `lite`. |
| `platform` | string | org default | VM platform, e.g. `windows`. |
| `max_acu_limit` | int | — | Cap ACU (compute) spend for this session. |
| `bypass_approval` | bool | — | Skip the approval gate. |
| `create_as_user_id` | string | — | Attribute the session to a user (needs `ImpersonateOrgSessions`). |
| `structured_output_required` | bool | `true` | Enforce the schema below. |
| `structured_output_schema` | object | — | JSON Schema **Draft 7**, ≤64 KB. See §6. |

Query param: `devin_id` _(optional; not normally used on create)_.

**Minimal example:**

```bash
curl -X POST "https://api.devin.ai/v3/organizations/$DEVIN_ORG_ID/sessions" \
  -H "Authorization: Bearer $DEVIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Upgrade flask to a non-vulnerable version, adapt call sites, run tests, open a PR."}'
```

**Response — `SessionResponse`** (same shape returned by *get* and *send message*):

| Field | Type | Notes |
| --- | --- | --- |
| `session_id` | string | The `devin-…` id. |
| `url` | string | Web UI link to the session. |
| `status` | enum | Lifecycle — see §5.2. |
| `status_detail` | enum \| null | Finer-grained reason — see §5.2. |
| `org_id` | string | |
| `user_id` / `service_user_id` | string \| null | Who created it. |
| `created_at` / `updated_at` | int | Unix epoch. |
| `acus_consumed` | number | Compute used so far. |
| `tags` | string[] | |
| `title` | string \| null | |
| `category` / `subcategory` | enum/string \| null | Auto-classification (see §5.5 enum). |
| `pull_requests` | SessionPullRequest[] | `{ pr_url, pr_state }` — **your main output for coding tasks.** |
| `parent_session_id` / `child_session_ids` | string / string[] \| null | Session trees. |
| `playbook_id` | string \| null | |
| `origin` | enum \| null | `webapp`, `slack`, `teams`, `api`, … |
| `is_archived` | bool | |
| `structured_output` | object \| null | Validated result object — **your main output for data tasks** (see §6). |

### 5.2 The lifecycle state machine

`status` (the coarse state):

| `status` | Terminal? | Meaning |
| --- | --- | --- |
| `new` | no | Created, not yet picked up. |
| `claimed` | no | A worker has it. |
| `running` | no | Actively working. |
| `resuming` | no | Coming back from suspension. |
| `suspended` | no | Paused. |
| `exit` | **yes** | Finished its run. |
| `error` | **yes** | Failed. |

`status_detail` (the *why* / blocked-reason — present mainly while non-terminal or
to explain a stop):

`working`, `waiting_for_user`, `waiting_for_approval`, `finished`, `inactivity`,
`user_request`, `usage_limit_exceeded`, `out_of_credits`, `out_of_quota`,
`no_quota_allocation`, `payment_declined`, `org_usage_limit_exceeded`,
`total_session_limit_exceeded`, `error`.

**How to poll correctly** (this is the crux of building on Devin):

```
loop:
  s = GET /sessions/{devin_id}
  if s.status in {exit, error}:                 -> DONE (success vs failure)
  if s.status_detail == waiting_for_user:       -> it's blocked on YOU: send a message (§5.4)
  if s.status_detail == waiting_for_approval:    -> approve, or create with bypass_approval
  if s.status_detail in {out_of_credits, *_limit_exceeded, payment_declined}:
                                                 -> stop; surface a billing/quota error
  else: sleep(backoff); continue
```

- **There is no webhook/push for session completion** in the documented API — poll
  `GET /sessions/{devin_id}`. Poll on an interval (e.g. 5–15s) with backoff; don't
  hammer it.
- `waiting_for_user` is not terminal — it means Devin asked a question. Your app
  should detect it, surface the latest Devin message, and `POST` a reply.
- On `exit`, read `pull_requests` and/or `structured_output` for the result. On
  `error`, inspect `status_detail`.

### 5.3 Get a session — `GET /v3/organizations/{org_id}/sessions/{devin_id}`

Returns the full `SessionResponse` above. Requires `ViewOrgSessions`. This is your
poll target.

### 5.4 Messages — read & send

**Read events** — `GET /v3/organizations/{org_id}/sessions/{devin_id}/messages`
(perm: `ViewOrgSessions`). Cursor-paginated (`first` 1–200, default 100; `after`).
Each item is a `SessionMessage`:

```jsonc
{ "event_id": "…", "source": "devin" | "user", "message": "…", "created_at": 1718000000 }
```

Use this to render a transcript and to read the question behind a `waiting_for_user`.

**Send a message** — `POST /v3/organizations/{org_id}/sessions/{devin_id}/messages`
(perm: `ManageOrgSessions`).

```jsonc
// body — SessionMessageCreateRequest
{ "message": "Also add unit tests.", "message_as_user_id": "user_abc123" /* optional */ }
```

Returns the updated `SessionResponse`. This both **answers a blocked session** and
**adds follow-up work** to a running/finished one.

### 5.5 List sessions — `GET /v3/organizations/{org_id}/sessions`

Returns `PaginatedResponse[SessionResponse]`. Rich server-side filters — push
filtering to the API, don't fetch-then-filter:

- Pagination: `first` (1–200, default 100), `after`.
- Time: `created_after`/`created_before`, `updated_after`/`updated_before` (epoch ints).
- Identity: `user_ids[]`, `service_user_ids[]`, `session_ids[]`.
- Provenance: `playbook_id`, `schedule_id`, `origins[]`
  (`webapp`,`slack`,`teams`,`api`,`linear`,`jira`,`automation`,`cli`,`desktop`,`code_scan`,`other`).
- Content: `tags[]`, `repo_names[]` (e.g. `"owner/repo"`), `is_archived`.
- `category` enum: `bug_fixing`, `ci_cd_and_devops`, `code_quality_and_security`,
  `code_review`, `code_review_and_analysis`, `data_and_automation`,
  `documentation_and_content`, `feature_development`, `migrations_and_upgrades`,
  `refactoring_and_optimization`, `research_and_exploration`, `security`,
  `unit_test_generation`, `other`.

### 5.6 Other session operations

| Op | Endpoint |
| --- | --- |
| Archive | `POST /v3/organizations/{org_id}/sessions/archive` |
| Delete | `DELETE …/sessions` |
| Tags (get/set/add/replace) | `…/sessions/{devin_id}/tags` (GET/POST/PUT) |
| Attachments on a session | `GET …/sessions/{devin_id}/attachments` |
| Insights | `…/sessions/{devin_id}/insights` (+ `…/insights/generate`) |

---

## 6. Structured output — the pattern that makes Devin programmable

For any task whose result your app must *parse* (not just "did a PR open?"),
constrain the output at creation:

```jsonc
{
  "prompt": "Audit dependencies with pip-audit and report each vulnerable package.",
  "structured_output_required": true,
  "structured_output_schema": {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
      "findings": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "package":  { "type": "string" },
            "cve":      { "type": "string" },
            "severity": { "type": "string", "enum": ["low","medium","high","critical"] }
          },
          "required": ["package", "severity"]
        }
      }
    },
    "required": ["findings"]
  }
}
```

Constraints: **JSON Schema Draft 7**, **≤64 KB**. When the session reaches `exit`,
read the validated object from `SessionResponse.structured_output`. This is how you
get machine-readable results back from an otherwise free-form agent — prefer it over
scraping `messages`.

---

## 7. Supporting resources (context you attach to sessions)

These let your app encode org conventions once and reuse them across sessions.

### 7.1 Knowledge notes — `…/knowledge/notes` (perm: `ManageAccountKnowledge`)

Standing context Devin pulls in when a trigger matches. **Create** (`POST`):

| Field | Type | Req | Notes |
| --- | --- | --- | --- |
| `name` | string | ✓ | Title. |
| `body` | string | ✓ | The content. |
| `trigger` | string | ✓ | When this note should apply. |
| `folder_id` | string \| null | | Organize into a folder. |
| `is_enabled` | bool \| null | | Toggle without deleting. |
| `pinned_repo` | string \| null | | Scope to a repo. |

Response `KnowledgeNoteResponse`: `note_id`, `name`, `body`, `trigger`, `folder_id`,
`folder_path`, `is_enabled`, `access_type` (`enterprise`\|`org`), `org_id`,
`macro`, `pinned_repo`, `created_at`, `updated_at`. Full CRUD: GET/POST/PUT/DELETE,
plus folders.

### 7.2 Playbooks — `…/playbooks` (perm: `ManageAccountPlaybooks`)

Reusable task templates. **Create** (`POST`):

| Field | Type | Req | Notes |
| --- | --- | --- | --- |
| `title` | string | ✓ | |
| `body` | string | ✓ | The playbook steps. |
| `macro` | string \| null | | `!`-prefixed, `[A-Za-z0-9_-]`, e.g. `!my_macro`. |

Response `PlaybookResponse`: `playbook_id`, `title`, `body`, `macro`, `access_type`,
`org_id`, `created_by`, `updated_by`, `created_at`, `updated_at`. Attach to a session
via `playbook_id` at creation.

### 7.3 Secrets — `…/secrets` (perm: `ManageOrgSecrets`)

Credentials Devin can use inside a session. **Create** (`POST`):

| Field | Type | Req | Default |
| --- | --- | --- | --- |
| `type` | enum `cookie`\|`key-value`\|`totp` | ✓ | |
| `key` | string | ✓ | |
| `value` | string | ✓ | |
| `is_sensitive` | bool | | `true` |
| `note` | string \| null | | |

Response `SecretResponse`: `secret_id`, `key`, `note`, `is_sensitive`,
`secret_type`, `access_type` (`org`\|`personal`), `created_by`, `created_at`,
`updated_by`, `updated_at`. The **value is write-only** — it is never returned.
Reference at session creation via `secret_ids[]`, or pass `session_secrets[]`
inline for one-off use.

### 7.4 Schedules — `…/schedules`

Run sessions on a cron (recurring) or at a future time (one-time). **Create**
(`POST`):

| Field | Type | Req | Notes |
| --- | --- | --- | --- |
| `name` | string | ✓ | |
| `prompt` | string | ✓ | What the scheduled session does. |
| `schedule_type` | string | | `recurring` (default) \| `one_time`. |
| `frequency` | string | | Cron expr, e.g. `0 9 * * 1-5` (weekday 9am). |
| `scheduled_at` | ISO 8601 | | For `one_time`; auto-disables after firing. |
| `interval_count` | int | | Default `1`. |
| `agent` | string | | `devin` (default) \| `data_analyst` \| `advanced`. |
| `playbook_id` | string | | |
| `platform` | string | | VM platform. |
| `bypass_approval` | bool | | Default `false`. |
| `notify_on` | string | | `failure` (default) \| `always` \| `never`. |
| `tags` | string[] | | |
| `create_as_user_id` | string | | Impersonation. |
| `slack_channel_id` / `slack_team_id` | string | | Slack routing. |
| `target_devin_id` | string | | Target session. |

Response `ScheduleResponse`: `scheduled_session_id`, `org_id`, `name`, `prompt`,
`agent`, `frequency`, `schedule_type`, `enabled`, `created_at`, `updated_at`,
`last_executed_at`, `last_error_at`, `last_error_message`, `consecutive_failures`,
`notify_on`, `playbook`, … Full lifecycle: GET/POST/PATCH/DELETE.

---

## 8. Attachments — `…/attachments` (perm: `UseDevinSessions`)

Two-step: **upload, then reference.**

1. **Upload** — `POST /v3/organizations/{org_id}/attachments`, `multipart/form-data`,
   field `file` (binary). Response: `{ attachment_id, name, url }`.
2. **Reference** — pass the returned `url` in `attachment_urls[]` when creating a
   session (each URL ≤2083 chars).

To retrieve files a session produced, use
`GET /v3/organizations/{org_id}/sessions/{devin_id}/attachments`.

---

## 9. The canonical "build an app" recipe

Everything above composes into one loop. This mirrors `backend/app/devin_client.py`
+ `orchestrator.py` in this repo (FastAPI + `httpx`).

```python
import time, httpx

BASE = "https://api.devin.ai/v3"

class Devin:
    def __init__(self, api_key: str, org_id: str, base_url: str = BASE):
        self.org = org_id
        self.http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    # healthcheck / key verification
    def verify(self) -> dict:
        r = self.http.get("/self")
        r.raise_for_status()
        return r.json()

    # 1. create
    def create_session(self, prompt: str, **opts) -> dict:
        r = self.http.post(f"/organizations/{self.org}/sessions",
                            json={"prompt": prompt, **opts})
        r.raise_for_status()
        return r.json()

    # 2. observe
    def get_session(self, devin_id: str) -> dict:
        r = self.http.get(f"/organizations/{self.org}/sessions/{devin_id}")
        r.raise_for_status()
        return r.json()

    # 3. respond when blocked / add follow-up work
    def send_message(self, devin_id: str, message: str) -> dict:
        r = self.http.post(f"/organizations/{self.org}/sessions/{devin_id}/messages",
                            json={"message": message})
        r.raise_for_status()
        return r.json()

    # 4. drive to a terminal state
    def run_to_completion(self, prompt: str, *, poll=10, timeout=3600, **opts) -> dict:
        s = self.create_session(prompt, **opts)
        devin_id = s["session_id"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            s = self.get_session(devin_id)
            if s["status"] in ("exit", "error"):
                return s                                  # done
            if s.get("status_detail") == "waiting_for_user":
                # surface the question; here we just nudge it along
                self.send_message(devin_id, "Please proceed with your best judgment.")
            time.sleep(poll)
        raise TimeoutError(f"{devin_id} did not finish within {timeout}s")
```

Then read results:

```python
result = devin.run_to_completion(
    "Upgrade vulnerable deps and open a PR.",
    title="security-remediation",
    tags=["security"],
)
if result["status"] == "exit":
    prs = result.get("pull_requests", [])          # coding output
    data = result.get("structured_output")          # data output (if schema set)
else:
    handle_failure(result.get("status_detail"))
```

**Scale-out pattern (this repo's orchestrator):** one discovery session returns N
findings (via `structured_output`), then fan out **one remediation session per
finding concurrently**, each polled independently, each opening its own PR. Sessions
are independent and cheap to create — parallelism is the intended usage.

---

## 10. Production checklist / gotchas

- **Poll, don't block.** No completion webhook is documented. Use a bounded poll
  loop with backoff and an overall timeout; persist the `session_id` so you can
  resume polling across restarts.
- **Handle `waiting_for_user`.** A session can stall waiting for input forever. Detect
  it, and either auto-reply, or surface the latest Devin message to a human.
- **Treat quota/billing `status_detail`s as terminal-ish.** `out_of_credits`,
  `*_limit_exceeded`, `payment_declined` won't fix themselves — alert, don't spin.
- **Cap spend with `max_acu_limit`** on untrusted/automated prompts.
- **Prefer `structured_output`** over parsing `messages` for any machine-consumed result.
- **Make base URL + key + org id config.** Enterprise hosts differ; keys rotate.
  Verify on boot with `GET /v3/self`.
- **Least privilege.** Member-role service user unless you truly need Admin/impersonation.
- **Idempotency.** The API has no documented idempotency key — guard against
  double-submits in your own layer (e.g. dedupe by finding id before creating).
- **Backoff on `429`.** Limits aren't published; assume they exist.
- **Secrets are write-only.** Store your own copy if you need the value; the API
  won't return it.
- **Demo/offline mode.** This repo simulates the full lifecycle when no `cog_` key
  is present — a good pattern for dev and tests without burning ACUs.

---

## 11. Endpoint index (v3)

Day-to-day **organization** surface for app builders:

```
Account     GET    /v3/self
Sessions    POST   /v3/organizations/{org}/sessions
            GET    /v3/organizations/{org}/sessions                 (list + filters)
            GET    /v3/organizations/{org}/sessions/{devin_id}
            GET    /v3/organizations/{org}/sessions/{devin_id}/messages
            POST   /v3/organizations/{org}/sessions/{devin_id}/messages
            GET    /v3/organizations/{org}/sessions/{devin_id}/attachments
            *      /v3/organizations/{org}/sessions/{devin_id}/tags  (GET/POST/PUT)
            POST   /v3/organizations/{org}/sessions/archive
Attachments POST   /v3/organizations/{org}/attachments               (multipart)
            GET    /v3/organizations/{org}/attachments
Knowledge   *      /v3/organizations/{org}/knowledge/notes           (CRUD) + /folders
Playbooks   *      /v3/organizations/{org}/playbooks                 (CRUD)
Secrets     *      /v3/organizations/{org}/secrets                   (CRUD)
Schedules   *      /v3/organizations/{org}/schedules                 (CRUD: GET/POST/PATCH/DELETE)
Repos       *      /v3/organizations/{org}/repositories…             (index/list/remove)
Git         *      /v3/organizations/{org}/git-providers…            (connections/permissions)
Snapshots   *      /v3/organizations/{org}/blueprints, /builds        (custom VM images)
```

**Enterprise / admin** surface (likely not needed for a single-org app): organizations,
members, users, roles, service-users, idp-groups, ip-access-list, hypervisors,
queue, metrics (`dau`/`wau`/`mau`/`prs`/`sessions`/`usage`/…), consumption,
audit-logs, guardrail-violations, pr-reviews — all under `/v3/enterprise/*` (with
org-scoped twins under `/v3/organizations/{org}/*` for metrics & consumption).

Full machine-readable list: **https://docs.devin.ai/llms.txt**

---

## 12. References

- Overview — https://docs.devin.ai/api-reference/overview
- Common flows — https://docs.devin.ai/api-reference/common-flows
- Authentication — https://docs.devin.ai/api-reference/authentication
- Teams quick start — https://docs.devin.ai/api-reference/getting-started/teams-quickstart
- Pagination — https://docs.devin.ai/api-reference/concepts/pagination
- v3 overview — https://docs.devin.ai/api-reference/v3/overview
- Create session — https://docs.devin.ai/api-reference/v3/sessions/post-organizations-sessions
- Machine-readable index — https://docs.devin.ai/llms.txt
- Support — support@cognition.ai

*Every doc URL has a `.md` twin (append `.md`) that returns clean markdown — ideal
for an agent to re-fetch a single endpoint's exact schema on demand.*
