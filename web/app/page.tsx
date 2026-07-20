"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Chart, registerables } from "chart.js";
import { assembleChartjs } from "flint-chart";

Chart.register(...registerables);

type Briefing = { source: string; artifacts: string; purpose: string; watch_for: string };
type FeedEvent = {
  kind: "probe" | "evidence";
  tool: string;
  source: string;
  briefing?: Briefing;
  summary?: string;
};
type State = {
  workspace: string;
  stats: Record<string, number>;
  objects: Array<{ type?: string; value?: string }>;
  briefings: Record<string, Briefing>;
};

function DistributionChart({ objects }: { objects: State["objects"] }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const object of objects) {
      const type = object.type ?? "unknown";
      result.set(type, (result.get(type) ?? 0) + 1);
    }
    return [...result].map(([type, count]) => ({ type, count }));
  }, [objects]);

  useEffect(() => {
    if (!canvas.current || counts.length === 0) return;
    const config = assembleChartjs({
      data: { values: counts },
      semantic_types: { type: "Category", count: "Quantity" },
      chart_spec: {
        chartType: "Bar Chart",
        encodings: { x: { field: "type" }, y: { field: "count" } },
        baseSize: { width: 620, height: 240 },
      },
    });
    const themedConfig = config as typeof config & { options?: Record<string, unknown> };
    themedConfig.options = {
      ...themedConfig.options,
      color: "#8ab8b3",
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#6d9894" }, grid: { color: "#123838" } },
        y: { ticks: { color: "#6d9894" }, grid: { color: "#123838" } },
      },
    };
    const datasets = (themedConfig.data as { datasets?: Array<Record<string, unknown>> }).datasets;
    for (const dataset of datasets ?? []) {
      dataset.backgroundColor = "rgba(69, 255, 229, .38)";
      dataset.borderColor = "#45ffe5";
      dataset.borderWidth = 1;
    }
    const chart = new Chart(canvas.current, themedConfig as never);
    return () => chart.destroy();
  }, [counts]);

  if (counts.length === 0) return <div className="empty-chart">NO ARTIFACTS IN VIEW</div>;
  return <canvas ref={canvas} aria-label="Artifact type distribution compiled by Flint" />;
}

export default function Cockpit() {
  const [state, setState] = useState<State | null>(null);
  const [feed, setFeed] = useState<FeedEvent[]>([]);
  const [target, setTarget] = useState("");
  const [active, setActive] = useState(false);
  const [error, setError] = useState("");

  const refresh = async () => {
    const response = await fetch("/api/state", { cache: "no-store" });
    setState(await response.json());
  };

  useEffect(() => {
    refresh().catch((reason) => setError(String(reason)));
  }, []);

  async function investigate(event: FormEvent) {
    event.preventDefault();
    const value = target.trim();
    if (!value || !state) return;
    setError("");
    setActive(true);
    try {
      const planResponse = await fetch(`/api/plan?target=${encodeURIComponent(value)}`, { cache: "no-store" });
      const plan = await planResponse.json();
      if (!planResponse.ok) throw new Error(plan.error ?? "Unable to plan investigation");
      setFeed(plan.events);
      const response = await fetch("/api/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: value }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error ?? "Investigation failed");
      setFeed(result.events);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setActive(false);
    }
  }

  return (
    <main>
      <header className="masthead">
        <div><span className="eyebrow">LOCAL INTELLIGENCE SYSTEM</span><h1>PIVOTGLASS</h1></div>
        <div className="system-state"><i className={active ? "pulse" : ""} />{active ? "HUNT ACTIVE" : "SYSTEM READY"}</div>
      </header>

      <section className="command-rail">
        <form onSubmit={investigate}>
          <span className="prompt">glass://investigate</span>
          <input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="domain, IP, URL, email, or hash" aria-label="Investigation target" />
          <button disabled={active}>{active ? "TRACKING…" : "ACQUIRE"}</button>
        </form>
        {error && <div className="error">FAULT · {error}</div>}
      </section>

      <section className="cockpit-grid">
        <article className="panel feed-panel">
          <div className="panel-title"><span>INTELLIGENCE STREAM</span><small>{feed.length} EVENTS</small></div>
          <div className="feed">
            {feed.length === 0 && <div className="standby"><b>AWAITING TARGET LOCK</b><span>Evidence, retrieval briefings, and pivots will appear here.</span></div>}
            {feed.map((item, index) => (
              <section className={`event ${item.kind}`} key={`${item.tool}-${item.kind}-${index}`}>
                <div className="event-head"><b>{item.kind.toUpperCase()}</b><span>{item.source}</span></div>
                {item.briefing && <>
                  <p><label>GATHER</label>{item.briefing.artifacts}</p>
                  <p><label>WHY</label>{item.briefing.purpose}</p>
                  <p><label>WATCH</label>{item.briefing.watch_for}</p>
                  <small>Retrieval goal—not an observed finding.</small>
                </>}
                {item.summary && <pre>{item.summary}</pre>}
              </section>
            ))}
          </div>
        </article>

        <aside className="right-stack">
          <article className="panel instruments">
            <div className="panel-title"><span>HUNT INSTRUMENTS</span><small>LIVE</small></div>
            <dl>
              <div><dt>WORKSPACE</dt><dd>{state?.workspace ?? "—"}</dd></div>
              <div><dt>ARTIFACTS</dt><dd>{state?.objects.length ?? 0}</dd></div>
              <div><dt>SOURCES</dt><dd>{Object.keys(state?.briefings ?? {}).length}</dd></div>
              <div><dt>TRANSPORT</dt><dd>LOOPBACK</dd></div>
            </dl>
          </article>
          <article className="panel chart-panel">
            <div className="panel-title"><span>ARTIFACT FIELD</span><small>FLINT / CHART.JS</small></div>
            <DistributionChart objects={state?.objects ?? []} />
          </article>
        </aside>
      </section>

      <footer><span>EVIDENCE ≠ INFERENCE</span><span>LOCALHOST · NO TELEMETRY · OPERATOR CONTROLLED</span></footer>
    </main>
  );
}
