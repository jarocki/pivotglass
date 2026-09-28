"use client";

type PegMotif = "empty" | "partial" | "filled" | "deferred" | "failed";

function motifForStatus(status: string): PegMotif {
  if (status === "filled" || status === "succeeded") return "filled";
  if (status === "empty") return "empty";
  if (status === "deferred" || status === "skipped" || status === "cancelled") {
    return "deferred";
  }
  if (status === "failed") return "failed";
  return "partial";
}

export function LiteBritePeg({
  status,
  label,
  compact = false,
}: {
  status: string;
  label: string;
  compact?: boolean;
}) {
  const motif = motifForStatus(status);

  return (
    <span
      className={`lite-brite-peg motif-${motif}${compact ? " compact" : ""}`}
      data-status={status}
      role="img"
      aria-label={label}
    >
      <svg viewBox="0 0 20 20" aria-hidden="true">
        {motif === "filled" ? <><circle cx="10" cy="10" r="8" fill="currentColor" /><path d="m6 10 3 3 5-6" className="peg-check" /></>
          : motif === "partial" ? <><circle cx="10" cy="10" r="7.5" /><path d="M10 2.5a7.5 7.5 0 0 0 0 15Z" fill="currentColor" stroke="none" /></>
          : motif === "deferred" ? <path d="M5 10h10" />
          : motif === "failed" ? <path d="m5 5 10 10M5 15 15 5" />
          : <circle cx="10" cy="10" r="6" />}
      </svg>
    </span>
  );
}
