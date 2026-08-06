import type { ReactNode } from "react";

export type BadgeArtworkProps = {
  badgeId?: string;
  kind?: string;
  glyph?: string;
  label: string;
  rarity?: string;
};

type BadgeVisual = { kind: string; glyph: string };

const BADGE_VISUALS: Record<string, BadgeVisual> = {
  "badge-first-blood": { kind: "first-signal", glyph: "1" },
  "badge-signal-trace": { kind: "evidence-lens", glyph: "5" },
  "badge-evidence-cache": { kind: "archive-stack", glyph: "25" },
  "badge-field-atlas": { kind: "route-map", glyph: "100" },
  "badge-deep-archive": { kind: "source-layers", glyph: "500" },
  "badge-data-hoarder": { kind: "archive-stack", glyph: "1K" },
  "badge-domain-scout": { kind: "domain-orbit", glyph: "10" },
  "badge-domain-hunter": { kind: "constellation", glyph: "50" },
  "badge-zone-mapper": { kind: "route-map", glyph: "100" },
  "badge-domain-atlas": { kind: "domain-orbit", glyph: "250" },
  "badge-network-scout": { kind: "network-grid", glyph: "10" },
  "badge-ip-collector": { kind: "network-grid", glyph: "50" },
  "badge-subnet-cartographer": { kind: "infrastructure-tower", glyph: "100" },
  "badge-address-space-atlas": { kind: "route-map", glyph: "250" },
  "badge-first-enrichment": { kind: "public-record", glyph: "1" },
  "badge-source-mixer": { kind: "source-layers", glyph: "3" },
  "badge-pivot-master": { kind: "pivot-nodes", glyph: "5" },
  "badge-persistent": { kind: "persistence-loop", glyph: "10" },
  "badge-long-watch": { kind: "time-watch", glyph: "25" },
  "badge-marathon-analyst": { kind: "lightning-map", glyph: "50" },
  "badge-century": { kind: "score-star", glyph: "100" },
  "badge-working-theory": { kind: "prediction-prism", glyph: "250" },
  "badge-grand-master": { kind: "grand-crown", glyph: "1K" },
  "badge-evidence-architect": { kind: "dossier-prism", glyph: "2.5K" },
  "badge-signal-sovereign": { kind: "trophy", glyph: "5K" },
  "badge-supreme-hunter": { kind: "trophy", glyph: "10K" },
  "badge-first-annotation": { kind: "notebook", glyph: "1" },
  "badge-case-journal": { kind: "notebook", glyph: "5" },
  "badge-note-taker": { kind: "public-record", glyph: "10" },
  "badge-analyst-ledger": { kind: "source-layers", glyph: "25" },
  "badge-chronicle-keeper": { kind: "archive-stack", glyph: "100" },
  "badge-facet-finder": { kind: "evidence-lens", glyph: "1" },
  "badge-half-the-picture": { kind: "dossier-prism", glyph: "5" },
  "badge-dossier-architect": { kind: "dossier-prism", glyph: "7" },
  "badge-dossier-complete": { kind: "dossier-prism", glyph: "9" },
  "badge-identity-first": { kind: "identity-key", glyph: "ID" },
  "badge-predictor": { kind: "prediction-prism", glyph: "3" },
  "badge-skeptic": { kind: "skeptic-scale", glyph: "?" },
  "badge-deception-spotter": { kind: "deception-eye", glyph: "!" },
  "badge-pioneer": { kind: "pioneer-compass", glyph: "N" },
};

const SUPPORTED_KINDS = [
  "field-mark", "crossbeam", "constellation", "public-record", "campaign-thread",
  "malware-signature", "actor-mask", "infrastructure-tower", "first-signal",
  "pivot-nodes", "persistence-loop", "archive-stack", "score-star", "grand-crown",
  "domain-orbit", "network-grid", "notebook", "dossier-prism", "identity-key",
  "prediction-prism", "skeptic-scale", "deception-eye", "pioneer-compass",
  "route-map", "source-layers", "time-watch", "trophy", "evidence-lens",
  "lightning-map",
] as const;

const FALLBACK_KINDS = SUPPORTED_KINDS.filter((kind) => kind !== "field-mark");

function stableIndex(value: string) {
  let hash = 0;
  for (const char of value) hash = ((hash * 31) + char.charCodeAt(0)) >>> 0;
  return hash % FALLBACK_KINDS.length;
}

export function resolveBadgeVisual(badgeId = "", kind?: string, glyph?: string): BadgeVisual {
  const catalog = BADGE_VISUALS[badgeId];
  const supported = kind && (SUPPORTED_KINDS as readonly string[]).includes(kind);
  return {
    kind: supported ? kind : (catalog?.kind ?? FALLBACK_KINDS[stableIndex(badgeId || "badge")]),
    glyph: glyph || catalog?.glyph || "◆",
  };
}

function artwork(kind: string): ReactNode {
  switch (kind) {
    case "crossbeam": return <><path className="badge-mark" d="M10 19q14-13 28 0M10 29q14 13 28 0M17 10q-13 14 0 28M31 10q13 14 0 28"/><circle className="badge-accent" cx="24" cy="24" r="4"/></>;
    case "constellation": return <><path className="badge-mark" d="M11 32 19 14l11 9 8-10"/><circle className="badge-accent" cx="11" cy="32" r="2"/><circle className="badge-accent" cx="19" cy="14" r="2"/><circle className="badge-accent" cx="30" cy="23" r="2"/><circle className="badge-accent" cx="38" cy="13" r="2"/></>;
    case "public-record": return <><path className="badge-mark" d="M15 9h14l6 6v24H15zM29 9v7h6M20 22h10M20 27h10M20 32h7"/><path className="badge-accent" d="M12 13h3M12 18h3M12 23h3"/></>;
    case "campaign-thread": return <><path className="badge-mark" d="M10 31c7-18 13 8 20-10s10 4 6 13"/><circle className="badge-accent" cx="10" cy="31" r="3"/><circle className="badge-accent" cx="30" cy="21" r="3"/><path className="badge-accent" d="m32 35 5-2-2-5"/></>;
    case "malware-signature": return <><path className="badge-mark" d="M17 18h14v15H17zM20 14h8M24 10v4M13 21h4M31 21h4M13 27h4M31 27h4M19 33l-3 5M29 33l3 5"/><path className="badge-accent" d="m20 23 3 3 5-6"/></>;
    case "actor-mask": return <><path className="badge-mark" d="M12 18q12-9 24 0l-3 15q-9 8-18 0zM17 23h6M27 23h5M20 30q4 3 8 0"/><path className="badge-accent" d="m14 17-3-5M34 17l3-5"/></>;
    case "infrastructure-tower": return <><path className="badge-mark" d="M15 38h18M19 37l5-27 5 27M18 28h12M20 20h8"/><circle className="badge-accent" cx="24" cy="9" r="2"/><path className="badge-accent" d="M15 15q9-8 18 0M11 11q13-12 26 0"/></>;
    case "first-signal": return <><path className="badge-mark" d="M24 24 38 13M24 24l-5 15M24 24 9 18"/><circle className="badge-accent" cx="24" cy="24" r="5"/><path className="badge-accent" d="M31 11h8v8"/></>;
    case "pivot-nodes": return <><path className="badge-mark" d="M14 15 33 12l3 22-22 2zM14 15l22 19M33 12 14 36"/><circle className="badge-accent" cx="14" cy="15" r="3"/><circle className="badge-accent" cx="33" cy="12" r="3"/><circle className="badge-accent" cx="36" cy="34" r="3"/><circle className="badge-accent" cx="14" cy="36" r="3"/></>;
    case "persistence-loop": return <><path className="badge-mark" d="M35 19a13 13 0 1 0 1 10M35 19v-8M35 19h-8"/><path className="badge-accent" d="M16 27a9 9 0 0 0 14 5"/></>;
    case "archive-stack": return <><path className="badge-mark" d="M11 14h26v8H11zM13 24h22v7H13zM16 33h16v6H16z"/><path className="badge-accent" d="M17 18h14M19 27h10"/></>;
    case "score-star": return <><path className="badge-mark" d="m24 8 4 10 11 1-8 7 3 11-10-6-10 6 3-11-8-7 11-1z"/><circle className="badge-accent" cx="24" cy="24" r="4"/></>;
    case "grand-crown": return <><path className="badge-mark" d="m10 16 8 8 6-13 6 13 8-8-4 21H14zM15 32h18"/><circle className="badge-accent" cx="10" cy="15" r="2"/><circle className="badge-accent" cx="24" cy="10" r="2"/><circle className="badge-accent" cx="38" cy="15" r="2"/></>;
    case "domain-orbit": return <><circle className="badge-mark" cx="24" cy="24" r="14"/><path className="badge-mark" d="M10 24h28M24 10c7 7 7 21 0 28M24 10c-7 7-7 21 0 28"/><path className="badge-accent" d="M8 13q16-11 32 0"/></>;
    case "network-grid": return <><path className="badge-mark" d="M12 12h8v8h-8zM28 12h8v8h-8zM12 28h8v8h-8zM28 28h8v8h-8zM20 16h8M16 20v8M32 20v8M20 32h8"/><circle className="badge-accent" cx="24" cy="24" r="3"/></>;
    case "notebook": return <><path className="badge-mark" d="M15 9h21v30H15zM12 14h6M12 20h6M12 26h6M12 32h6M21 17h10M21 23h10M21 29h7"/><path className="badge-accent" d="m28 35 8-8"/></>;
    case "dossier-prism": return <><path className="badge-mark" d="m24 7 15 9v17l-15 9-15-9V16zM9 16l15 9 15-9M24 25v17"/><path className="badge-accent" d="m24 7 0 18"/></>;
    case "identity-key": return <><circle className="badge-mark" cx="17" cy="19" r="8"/><path className="badge-mark" d="m23 25 14 14M31 33l4-4M27 29l4-4"/><circle className="badge-accent" cx="17" cy="19" r="3"/></>;
    case "prediction-prism": return <><path className="badge-mark" d="m24 8 15 28H9zM24 8v28M9 36l15-9 15 9"/><path className="badge-accent" d="m18 22 5 4 8-9"/></>;
    case "skeptic-scale": return <><path className="badge-mark" d="M24 10v27M14 15h20M12 16l-5 11h10zM36 16l-5 11h10zM17 38h14"/><path className="badge-accent" d="M15 11q9-5 18 0"/></>;
    case "deception-eye": return <><path className="badge-mark" d="M7 24q17-18 34 0-17 18-34 0z"/><circle className="badge-accent" cx="24" cy="24" r="6"/><path className="badge-accent" d="m13 36 22-24"/></>;
    case "pioneer-compass": return <><circle className="badge-mark" cx="24" cy="24" r="15"/><path className="badge-mark" d="m29 18-5 16-5-11z"/><path className="badge-accent" d="M24 6v5M24 37v5M6 24h5M37 24h5"/></>;
    case "route-map": return <><path className="badge-mark" d="M10 36 17 13l14 6 7-9v25l-14 5zM17 13v22M31 19v17"/><path className="badge-accent" d="m12 30 8-6 8 5 8-10"/></>;
    case "source-layers": return <><path className="badge-mark" d="m24 9 16 8-16 8-16-8zM8 24l16 8 16-8M8 31l16 8 16-8"/><path className="badge-accent" d="m17 17 7 3 7-3"/></>;
    case "time-watch": return <><circle className="badge-mark" cx="24" cy="25" r="14"/><path className="badge-mark" d="M20 8h8M20 42h8M24 25V15M24 25l8 5"/><path className="badge-accent" d="m34 12 4 4"/></>;
    case "trophy": return <><path className="badge-mark" d="M15 10h18v10q0 12-9 12t-9-12zM15 14H9q0 11 8 11M33 14h6q0 11-8 11M24 32v6M17 39h14"/><path className="badge-accent" d="m24 15 2 4 5 1-4 3 1 5-4-3-4 3 1-5-4-3 5-1z"/></>;
    case "evidence-lens": return <><circle className="badge-mark" cx="20" cy="20" r="11"/><path className="badge-mark" d="m28 28 11 11"/><path className="badge-accent" d="M14 20h12M20 14v12"/></>;
    case "lightning-map": return <><path className="badge-mark" d="M10 12h11l4 6 6-6h7v24H27l-4-5-6 5h-7z"/><path className="badge-accent" d="m27 8-8 16h7l-5 16 13-20h-8z"/></>;
    default: return <><path className="badge-mark" d="m24 8 15 16-15 16L9 24z"/><circle className="badge-accent" cx="24" cy="24" r="7"/></>;
  }
}

export function BadgeArtwork({ badgeId = "", kind, glyph, label, rarity = "common" }: BadgeArtworkProps) {
  const visual = resolveBadgeVisual(badgeId, kind, glyph);
  const safeRarity = ["common", "uncommon", "rare", "epic", "legendary"].includes(rarity) ? rarity : "common";
  return <svg className={`badge-art badge-art-${visual.kind} rarity-${safeRarity}`} data-artwork={visual.kind} viewBox="0 0 48 48" role="img" aria-label={label}>
    <circle className="badge-shell" cx="24" cy="24" r="22" />
    {artwork(visual.kind)}
    <text className="badge-glyph" x="24" y="46">{visual.glyph}</text>
  </svg>;
}

export const BADGE_ARTWORK_KINDS = SUPPORTED_KINDS;
