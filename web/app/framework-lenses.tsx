"use client";

export type FrameworkState = {
  versions: Record<"attack" | "kill_chain" | "diamond", string>;
  counts: Partial<Record<"attack" | "kill_chain" | "diamond", Record<string, number>>>;
  principles: Record<"attack" | "kill_chain" | "diamond", string>;
};

const LABELS = {
  attack: "MITRE ATT&CK",
  kill_chain: "CYBER KILL CHAIN",
  diamond: "DIAMOND MODEL",
} as const;

export function FrameworkLenses({
  frameworks,
  onCommand,
}: {
  frameworks: FrameworkState;
  onCommand: (command: string) => void;
}) {
  const keys = Object.keys(LABELS) as Array<keyof typeof LABELS>;
  const accepted = keys.reduce((total, key) => total + (frameworks.counts[key]?.accepted ?? 0), 0);
  const proposed = keys.reduce((total, key) => total + (frameworks.counts[key]?.proposed ?? 0), 0);
  return <details className="framework-lenses">
    <summary>
      <span><b>FRAMEWORK PERSPECTIVES</b><small>Three lenses over the same evidence—not three competing truths</small></span>
      <i>{accepted} ACCEPTED · {proposed} AWAITING REVIEW</i>
    </summary>
    <p className="framework-truth-label">Mappings are analytical claims. Full evidence references, basis, confidence, and analyst disposition appear only when explicitly requested.</p>
    <div className="framework-lens-grid">
      {keys.map((framework) => {
        const counts = frameworks.counts[framework] ?? {};
        return <section key={framework}>
          <header><div><b>{LABELS[framework]}</b><small>VERSION {frameworks.versions[framework]}</small></div><span>{counts.accepted ?? 0} ACCEPTED · {counts.proposed ?? 0} PROPOSED</span></header>
          <p>{frameworks.principles[framework]}</p>
          <button onClick={() => onCommand(`framework show ${framework}`)}>OPEN EVIDENCE-BACKED VIEW</button>
        </section>;
      })}
    </div>
    <footer><button onClick={() => onCommand("framework manifest")}>CONTENT MANIFEST</button><button onClick={() => onCommand("framework navigator")}>EXPORT ATT&amp;CK NAVIGATOR</button></footer>
  </details>;
}
