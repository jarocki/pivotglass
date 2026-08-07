export type NarrationPreference = "full" | "brief" | "off";

export const ADVISOR_IDLE_MS: Record<Exclude<NarrationPreference, "off">, number> = {
  full: 5 * 60_000,
  brief: 8 * 60_000,
};

export const ADVISOR_COOLDOWN_MS = 15 * 60_000;

export function advisorCanInterrupt({
  now,
  lastActivityAt,
  lastPresentedAt,
  narration,
  busy,
  overlayOpen,
  adviceVisible,
}: {
  now: number;
  lastActivityAt: number;
  lastPresentedAt: number;
  narration: NarrationPreference;
  busy: boolean;
  overlayOpen: boolean;
  adviceVisible: boolean;
}) {
  if (narration === "off" || busy || overlayOpen || adviceVisible) return false;
  return (
    now - lastActivityAt >= ADVISOR_IDLE_MS[narration]
    && now - lastPresentedAt >= ADVISOR_COOLDOWN_MS
  );
}
