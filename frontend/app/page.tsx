"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Health,
  type Metrics,
  type Run,
  type RemediationSession,
  type Vertical,
} from "../lib/api";

const POLL_MS = 2500;

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

  return (
    <div className="wrap">
      <header className="top">
        <div>
          <h1>Devin Remediation Control</h1>
          <div className="subtitle">
            Event-driven autonomous remediation for{" "}
            {health?.github_repo ?? "apache/superset"}
          </div>
        </div>
        {health && (
          <span className={`badge ${health.demo_mode ? "demo" : "live"}`}>
            <span className="dot working" />
            {health.demo_mode ? "DEMO MODE" : "LIVE · Devin v3"}
          </span>
        )}
      </header>

      <div className="controls">
        <span className="muted">Trigger remediation for:</span>
        <select
          value={vertical}
          onChange={(e) => setVertical(e.target.value as Vertical)}
        >
          <option value="both">Both verticals</option>
          <option value="security">Security (urgent CVEs)</option>
          <option value="backlog">Backlog (code-quality toil)</option>
        </select>
        <button className="primary" onClick={trigger} disabled={triggering}>
          {triggering ? "Triggering…" : "▶ Run Remediation"}
        </button>
        <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>
          event trigger → discovery session → per-issue fix sessions → PRs
        </span>
      </div>

      {error && (
        <div className="empty" style={{ color: "var(--red)" }}>
          {error}
        </div>
      )}

      <MetricsRow m={metrics} />

      <div className="section-title">Runs</div>
      {runs.length === 0 ? (
        <div className="empty">
          No runs yet. Click <b>Run Remediation</b> to dispatch Devin.
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
  );
}

function MetricsRow({ m }: { m: Metrics | null }) {
  const cells = [
    { k: "PRs opened", v: m?.prs_opened ?? 0 },
    { k: "Succeeded", v: m?.succeeded ?? 0 },
    { k: "In progress", v: m?.in_progress ?? 0 },
    {
      k: "Success rate",
      v: m ? `${Math.round(m.success_rate * 100)}%` : "—",
    },
    { k: "Vulns remediated", v: m?.vulns_remediated ?? 0 },
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
        <div>
          <span className="id">{run.id}</span>{" "}
          <span className="muted" style={{ fontSize: 12 }}>
            · {run.vertical}
          </span>
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
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          Discovery:{" "}
          <a href={run.discovery_session_url} target="_blank" rel="noreferrer">
            view Devin session ↗
          </a>{" "}
          · {run.findings.length} issues found
        </div>
      )}

      {run.sessions.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Finding</th>
              <th>Type</th>
              <th>Devin session</th>
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
          Impact:&nbsp;
          <span>
            vulnerabilities {before} → <b>{after}</b>
          </span>
          {run.after?.any_types != null && (
            <span>· any-types remaining: {run.after.any_types}</span>
          )}
        </div>
      )}

      {run.phase === "completed" && (
        <button
          className="ghost"
          style={{ marginTop: 12 }}
          onClick={onVerify}
        >
          ↻ Re-scan (verify post-merge impact)
        </button>
      )}
      {run.error && <div className="fail">Error: {run.error}</div>}
    </div>
  );
}

function SessionRow({ s }: { s: RemediationSession }) {
  return (
    <tr>
      <td>{s.finding_title}</td>
      <td>
        <span className={`vtag ${s.vertical}`}>{s.vertical}</span>
      </td>
      <td>
        {s.session_url ? (
          <a href={s.session_url} target="_blank" rel="noreferrer">
            {s.session_id ?? "open"} ↗
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
          <a href={s.pr_url} target="_blank" rel="noreferrer">
            PR ↗
          </a>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
    </tr>
  );
}
