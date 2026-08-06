"use client";

import type { CSSProperties } from "react";

import { rgbForStatus } from "./rgb-led";

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

export function LiteBritePeg({ status, label }: { status: string; label: string }) {
  const [red, green, blue] = rgbForStatus(status);
  const motif = motifForStatus(status);
  const style = {
    "--peg-rgb": `rgb(${red} ${green} ${blue})`,
  } as CSSProperties;

  return (
    <span
      className={`lite-brite-peg motif-${motif}`}
      style={style}
      data-status={status}
      data-rgb={`${red},${green},${blue}`}
      role="img"
      aria-label={label}
    >
      <i className="peg-outer" aria-hidden="true" />
      <i className="peg-middle" aria-hidden="true" />
      <i className="peg-inner" aria-hidden="true" />
      <i className="peg-center" aria-hidden="true" />
    </span>
  );
}
