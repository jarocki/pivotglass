/**
 * View preferences: the single authority for how the cockpit uses the screen
 * (DEC-VIEW-PREFERENCES-001). Width, text size, density, and the optional
 * attention spotlight are analyst choices, never inferred from diagnosis,
 * device, or behaviour. Stored per browser under one versioned key.
 */

export type ViewWidth = "column" | "wide" | "full";
export type TextSize = "compact" | "standard" | "large" | "xlarge";
export type Density = "comfortable" | "compact";
export type ViewPreferences = { width: ViewWidth; text: TextSize; density: Density; spotlight: boolean };

export const VIEW_KEY = "pivotglass.view.v1";
/** Superseded key from v1.2: only ``textSize: "large"`` and ``spotlight`` carry over. */
export const LEGACY_READING_KEY = "pivotglass.reading.v1";

export const WIDTHS: Array<{ value: ViewWidth; label: string }> = [
  { value: "column", label: "Column" }, { value: "wide", label: "Wide" }, { value: "full", label: "Full" },
];
export const TEXT_SIZES: Array<{ value: TextSize; label: string; percent: number }> = [
  { value: "compact", label: "Compact", percent: 81.25 },
  { value: "standard", label: "Standard", percent: 87.5 },
  { value: "large", label: "Large", percent: 100 },
  { value: "xlarge", label: "Extra large", percent: 112.5 },
];
export const DENSITIES: Array<{ value: Density; label: string }> = [
  { value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" },
];

export const DEFAULT_VIEW: ViewPreferences = { width: "wide", text: "standard", density: "comfortable", spotlight: false };

function record(raw: string | null): Record<string, unknown> | null {
  try {
    const value: unknown = raw ? JSON.parse(raw) : null;
    return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
  } catch { return null; }
}

function pick<T extends string>(value: unknown, allowed: Array<{ value: T }>, fallback: T): T {
  return allowed.some((item) => item.value === value) ? value as T : fallback;
}

/** Parse stored preferences; unknown or malformed fields fall back to defaults. */
export function readViewPreferences(raw: string | null, legacyReading: string | null = null): ViewPreferences {
  const data = record(raw);
  if (data) {
    return {
      width: pick(data.width, WIDTHS, DEFAULT_VIEW.width),
      text: pick(data.text, TEXT_SIZES, DEFAULT_VIEW.text),
      density: pick(data.density, DENSITIES, DEFAULT_VIEW.density),
      spotlight: data.spotlight === true,
    };
  }
  const legacy = record(legacyReading);
  return { ...DEFAULT_VIEW, text: legacy?.textSize === "large" ? "large" : DEFAULT_VIEW.text, spotlight: legacy?.spotlight === true };
}

/** Step text size up or down, clamped to the available steps. */
export function stepTextSize(current: TextSize, direction: 1 | -1): TextSize {
  const index = TEXT_SIZES.findIndex((item) => item.value === current);
  return TEXT_SIZES[Math.max(0, Math.min(TEXT_SIZES.length - 1, index + direction))]!.value;
}

export function nextWidth(current: ViewWidth): ViewWidth {
  const index = WIDTHS.findIndex((item) => item.value === current);
  return WIDTHS[(index + 1) % WIDTHS.length]!.value;
}

export function rootFontPercent(text: TextSize): number {
  return TEXT_SIZES.find((item) => item.value === text)!.percent;
}
