export type ReadingPreferences = { textSize: "standard" | "large"; spotlight: boolean };
export const DEFAULT_READING: ReadingPreferences = { textSize: "standard", spotlight: false };

/** Preferences are choices, never guesses based on diagnosis or performance. */
export function readReadingPreferences(raw: string | null): ReadingPreferences {
  try {
    const value: unknown = raw ? JSON.parse(raw) : null;
    if (!value || typeof value !== "object" || Array.isArray(value)) return { ...DEFAULT_READING };
    const data = value as Record<string, unknown>;
    return { textSize: data.textSize === "large" ? "large" : "standard", spotlight: data.spotlight === true };
  } catch { return { ...DEFAULT_READING }; }
}
