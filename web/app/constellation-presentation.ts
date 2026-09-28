/** Presentation labels only: coverage must never become a threat verdict. */
export const COVERAGE_LABELS: Readonly<Record<string, string>> = {
  filled: "Coverage met", partial: "Some evidence", empty: "No evidence", deferred: "No automated path",
};

export function indicatorTypeLabel(type: string): string {
  return ({ "ipv4-addr": "IPv4", "ipv6-addr": "IPv6", "domain-name": "Domain",
    "email-addr": "Email", url: "URL", file: "File" } as Record<string, string>)[type]
    ?? type.replaceAll("_", " ");
}

export function reportedCountry(code: unknown): { flag: string; name: string; code: string } | null {
  if (typeof code !== "string" || !/^[A-Z]{2}$/.test(code)) return null;
  const name = new Intl.DisplayNames(["en"], { type: "region", fallback: "none" }).of(code);
  if (!name || name === "Unknown Region" || code === "EU" || code === "UN") return null;
  return { code, name, flag: String.fromCodePoint(...[...code].map((c) => c.charCodeAt(0) + 127397)) };
}

export function tooltipPosition(anchor: { left: number; top: number; bottom: number },
  size: { width: number; height: number }, viewport: { width: number; height: number }) {
  const margin = 12;
  const below = anchor.bottom + 8;
  return {
    left: Math.max(margin, Math.min(anchor.left, viewport.width - size.width - margin)),
    top: Math.max(margin, Math.min(below + size.height <= viewport.height - margin
      ? below : anchor.top - size.height - 8, viewport.height - size.height - margin)),
  };
}
