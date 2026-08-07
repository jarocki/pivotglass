"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type ActivityEvent = {
  event_id: string;
  sequence: number;
  event_class: string;
  severity: string;
  lifecycle: string;
  content_class: "evidence" | "narration" | "system";
  created_at: string;
  target: string;
  tool?: string | null;
  source?: string | null;
  summary?: string | null;
  reason?: string | null;
  next_action?: string | null;
  diagnostic_id?: string | null;
  diagnostic_category?: string | null;
  log_name?: string | null;
};

type Authority = {
  id: string;
  label: string;
  kind: string;
  authority: string;
  state: "ready" | "degraded" | "disabled" | "missing_configuration" | "unavailable";
  reason: string;
  credential_source?: string;
  background_network: boolean;
};

export type ActivityState = {
  events: ActivityEvent[];
  event_limit: number;
  notice: string;
  registry: {
    state: string;
    counts: Record<string, number>;
    authorities: Authority[];
    offline_behavior: string;
  };
};

function eventText(event: ActivityEvent) {
  return event.summary ?? event.reason ?? event.next_action ?? event.lifecycle;
}

function timeLabel(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleTimeString([], { hour12: false });
}

export function ActivityTerminal({
  activity,
  onDiagnostic,
}: {
  activity: ActivityState;
  onDiagnostic: (diagnosticId: string) => void;
}) {
  const [severity, setSeverity] = useState("all");
  const [paused, setPaused] = useState(false);
  const [frozen, setFrozen] = useState<ActivityEvent[]>([]);
  const [clearedThrough, setClearedThrough] = useState(0);
  const viewport = useRef<HTMLDivElement>(null);
  const sourceEvents = paused ? frozen : activity.events;
  const visible = useMemo(
    () => sourceEvents.slice(clearedThrough).filter((event) => severity === "all" || event.severity === severity),
    [clearedThrough, severity, sourceEvents],
  );

  useEffect(() => {
    if (!paused) viewport.current?.scrollTo({ top: viewport.current.scrollHeight });
  }, [paused, visible.length]);

  useEffect(() => {
    if (!paused && clearedThrough > activity.events.length) setClearedThrough(0);
  }, [activity.events.length, clearedThrough, paused]);

  function togglePause() {
    if (!paused) setFrozen(activity.events);
    setPaused((current) => !current);
  }

  function download() {
    const content = JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        notice: activity.notice,
        registry: activity.registry,
        events: visible,
      },
      null,
      2,
    );
    const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "pivotglass-sanitized-activity.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="activity-terminal" aria-label="Activity and errors terminal">
      <header>
        <div><b>ACTIVITY &amp; ERRORS</b><span>{visible.length} VISIBLE · {activity.registry.state.toUpperCase()}</span></div>
        <div className="activity-controls">
          <label>SHOW <select aria-label="Activity severity" value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="all">all</option><option value="info">info</option><option value="warning">warning</option><option value="error">error</option></select></label>
          <button onClick={togglePause}>{paused ? "RESUME FOLLOW" : "PAUSE FOLLOW"}</button>
          <button onClick={() => setClearedThrough(sourceEvents.length)}>CLEAR VIEW</button>
          <button onClick={download}>DOWNLOAD SANITIZED</button>
        </div>
      </header>
      <div className="activity-scroll" ref={viewport} tabIndex={0} aria-label="Scrollable activity history">
        {visible.length === 0 && <p>— No events in this view. System state remains available below. —</p>}
        {visible.map((event) => (
          <article className={`severity-${event.severity} class-${event.event_class}`} key={event.event_id}>
            <time>{timeLabel(event.created_at)}</time>
            <b>{event.severity.toUpperCase()}</b>
            <span>{event.tool ?? event.source ?? event.event_class}</span>
            <p>{eventText(event)}</p>
            {event.next_action && <small>NEXT: {event.next_action}</small>}
            {event.diagnostic_id && <button onClick={() => onDiagnostic(event.diagnostic_id!)}>{event.log_name ?? "diagnostic"} · {event.diagnostic_id}</button>}
          </article>
        ))}
      </div>
      <details className="authority-registry">
        <summary><b>OPERATIONAL AUTHORITIES</b><span>{activity.registry.counts.ready ?? 0} READY · {activity.registry.counts.degraded ?? 0} DEGRADED · {activity.registry.counts.missing_configuration ?? 0} MISSING CONFIG</span></summary>
        <p>{activity.registry.offline_behavior}</p>
        <div>{activity.registry.authorities.map((authority) => (
          <article key={authority.id}>
            <span className={`authority-state state-${authority.state}`}>{authority.state.replaceAll("_", " ")}</span>
            <b>{authority.label}</b>
            <small>{authority.authority}</small>
            <p>{authority.reason}</p>
          </article>
        ))}</div>
      </details>
      <small className="activity-notice">{activity.notice}</small>
    </section>
  );
}
