"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type Health,
  type Metrics,
  type Run,
  type RemediationSession,
  type Vertical,
} from "../lib/api";

const POLL_MS = 2500;

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function CognitionLogo({ size = 28 }: { size?: number }) {
  return (
    <img
      src="/cognition_logo.jpg"
      alt="Cognition"
      width={size}
      height={size}
      style={{ borderRadius: 4, objectFit: "contain" }}
    />
  );
}

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [vertical, setVertical] = useState<Vertical>("both");
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [m, r] = await Promise.all([api.metrics(), api.listRuns()]);
      setMetrics(m);
      setRuns(r);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => {});
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const trigger = async () => {
    setTriggering(true);
    try {
      await api.triggerRun(vertical);
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setTriggering(false);
    }
  };

  const verify = async (id: string) => {
    await api.verifyImpact(id);
    await refresh();
  };

  const stop = async (id: string) => {
    await api.stopRun(id);
    await refresh();
  };

  const activeRuns = runs.filter((r) =>
    ["discovering", "remediating"].includes(r.phase)
  );

  return (
    <div className="layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <CognitionLogo size={28} />
          <span>Cognition</span>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-item active">
            <svg className="nav-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="8" cy="8" r="6.5" />
              <path d="M5.5 8l2 2 3-3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Superset Automations
          </div>
        </nav>

        {runs.length > 0 && (
          <>
            <div className="sidebar-section">Recent runs</div>
            {runs.slice(0, 5).map((r) => (
              <div className="sidebar-run-item" key={r.id}>
                <div className="run-name">{r.vertical} · {r.phase}</div>
                <div className="run-age">{timeAgo(r.created_at)}</div>
              </div>
            ))}
          </>
        )}
      </aside>

      {/* Main content */}
      <div className="main">
        <div className="topbar">
          <span className="topbar-title">Superset Automations</span>
          <div className="topbar-right">
            {activeRuns.length > 0 && (
              <span style={{ fontSize: 12, color: "var(--muted)", display: "flex", alignItems: "center", gap: 6 }}>
                <span className="dot working" />
                {activeRuns.length} active
              </span>
            )}
            {health && (
              <span className={`mode-badge ${health.demo_mode ? "demo" : "live"}`}>
                <span className={`dot ${health.demo_mode ? "pending" : "working"}`} />
                {health.demo_mode ? "Demo mode" : "Live · Devin v3"}
              </span>
            )}
          </div>
        </div>

        <div className="content">
          {error && <div className="error-banner">{error}</div>}

          {/* Trigger panel */}
          <div className="trigger-panel">
            <div className="trigger-panel-title">Remediation Engineer</div>
            <div className="trigger-row">
              <VerticalSelect value={vertical} onChange={setVertical} />
              <button className="primary" onClick={trigger} disabled={triggering}>
                {triggering ? (
                  <>
                    <span className="dot working" style={{ width: 6, height: 6 }} />
                    Dispatching…
                  </>
                ) : (
                  <>
                    <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M3 2l11 6-11 6V2z" />
                    </svg>
                    Run remediation
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Metrics */}
          <MetricsRow m={metrics} />

          {/* Runs */}
          <div className="section-title">Runs</div>
          {runs.length === 0 ? (
            <div className="empty-state">
              <svg className="empty-icon" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="20" cy="20" r="18" />
                <path d="M13 20l5 5 9-9" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span>
                No runs yet. Click <b>Run remediation</b> to dispatch Devin.
              </span>
            </div>
          ) : (
            runs.map((run) => (
              <RunCard
                key={run.id}
                run={run}
                onVerify={() => verify(run.id)}
                onStop={() => stop(run.id)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function MetricsRow({ m }: { m: Metrics | null }) {
  const cells = [
    { k: "Sessions in progress", v: m?.in_progress ?? 0 },
    { k: "PRs opened", v: m?.prs_opened ?? 0 },
    { k: "Succeeded", v: m?.succeeded ?? 0 },
    { k: "Success rate", v: m ? `${Math.round(m.success_rate * 100)}%` : "—" },
    { k: "Vulnerabilities fixed", v: m?.vulns_remediated ?? 0 },
    { k: "Code quality fixed", v: m?.backlog_fixed ?? 0 },
  ];
  return (
    <div className="metrics">
      {cells.map((c) => (
        <div className="metric" key={c.k}>
          <div className="v">{c.v}</div>
          <div className="k">{c.k}</div>
        </div>
      ))}
    </div>
  );
}

function RunCard({
  run,
  onVerify,
  onStop,
}: {
  run: Run;
  onVerify: () => void;
  onStop: () => void;
}) {
  const before = (run.before?.py_vulns ?? 0) + (run.before?.npm_vulns ?? 0);
  const after = (run.after?.py_vulns ?? 0) + (run.after?.npm_vulns ?? 0);
  const hasDelta = run.before != null && run.after != null;
  const active = run.phase === "discovering" || run.phase === "remediating";

  return (
    <div className="run">
      <div className="run-head">
        <div className="run-head-left">
          <span className="run-id">{run.id}</span>
          <span className="run-vertical">{run.vertical}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {active && (
            <button className="ghost stop" onClick={onStop}>
              ■ Stop
            </button>
          )}
          <span className={`phase ${run.phase}`}>{run.phase}</span>
        </div>
      </div>

      {run.discovery_session_url && (
        <div className="discovery-link">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="6.5" />
            <path d="M8 5v4l2.5 2.5" strokeLinecap="round" />
          </svg>
          Discovery session:{" "}
          <a href={run.discovery_session_url} target="_blank" rel="noreferrer">
            view in Devin ↗
          </a>
          {" · "}
          {run.findings.length} issue{run.findings.length !== 1 ? "s" : ""} found
        </div>
      )}

      {run.sessions.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Finding</th>
              <th>Type</th>
              <th>Session</th>
              <th>Status</th>
              <th>Tests</th>
              <th>PR</th>
            </tr>
          </thead>
          <tbody>
            {run.sessions.map((s) => (
              <SessionRow key={s.finding_id} s={s} />
            ))}
          </tbody>
        </table>
      )}

      {hasDelta && (
        <div className="impact">
          <span className="impact-label">Impact</span>
          <span>
            Vulnerabilities{" "}
            <span style={{ color: "var(--text-2)", fontWeight: 500 }}>{before}</span>
            {" → "}
            <span className="impact-delta">{after}</span>
          </span>
          {run.after?.any_types != null && (
            <span>any-types remaining: {run.after.any_types}</span>
          )}
        </div>
      )}

      {(run.phase === "completed" || run.error) && (
        <div className="run-actions">
          {run.phase === "completed" && (
            <button className="ghost" onClick={onVerify}>
              ↻ Re-scan to verify impact
            </button>
          )}
          {run.error && (
            <span style={{ fontSize: 12, color: "var(--red)" }}>
              Error: {run.error}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function SessionRow({ s }: { s: RemediationSession }) {
  return (
    <tr>
      <td style={{ color: "var(--text)", fontWeight: 450 }}>{s.finding_title}</td>
      <td>
        <span className={`vtag ${s.vertical}`}>{s.vertical}</span>
      </td>
      <td>
        {s.session_url ? (
          <a href={s.session_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
            {s.session_id?.slice(0, 12) ?? "open"} ↗
          </a>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td>
        <span className="status">
          <span className={`dot ${s.status}`} />
          {s.status}
        </span>
      </td>
      <td>
        {s.tests_pass == null ? (
          <span className="muted">—</span>
        ) : s.tests_pass ? (
          <span className="pass">pass</span>
        ) : (
          <span className="fail">fail</span>
        )}
      </td>
      <td>
        {s.pr_url ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <a href={s.pr_url} target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>
              View PR ↗
            </a>
            {s.is_draft && <span className="draft-tag">draft</span>}
          </span>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
    </tr>
  );
}

const VERTICAL_OPTIONS: {
  value: Vertical;
  label: string;
  dots: ("red" | "blue")[];
}[] = [
  { value: "both", label: "Both verticals", dots: ["red", "blue"] },
  { value: "security", label: "CVEs only", dots: ["red"] },
  { value: "backlog", label: "Code quality only", dots: ["blue"] },
];

function Dots({ dots }: { dots: ("red" | "blue")[] }) {
  return (
    <span className="vdots">
      {dots.map((d, i) => (
        <span key={i} className={`vdot ${d}`} />
      ))}
    </span>
  );
}

function VerticalSelect({
  value,
  onChange,
}: {
  value: Vertical;
  onChange: (v: Vertical) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const current = VERTICAL_OPTIONS.find((o) => o.value === value)!;

  return (
    <div className="vselect" ref={ref}>
      <button
        type="button"
        className="vselect-trigger"
        onClick={() => setOpen((o) => !o)}
      >
        <Dots dots={current.dots} />
        <span>{current.label}</span>
        <svg
          className="vselect-caret"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="vselect-menu">
          {VERTICAL_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              className={`vselect-option ${o.value === value ? "selected" : ""}`}
              onClick={() => {
                onChange(o.value);
                setOpen(false);
              }}
            >
              <Dots dots={o.dots} />
              <span>{o.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
