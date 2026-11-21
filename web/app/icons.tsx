/*
 * One authority for interface glyphs. Icons follow the conventions analysts already know
 * from desktop and web apps (maximize = outward corners, restore = inward corners, pop out =
 * box with an outbound arrow). Every icon button must still carry an aria-label and a title,
 * so the action is named for screen readers and on hover; words appear on a button only when
 * an icon alone would be ambiguous.
 */
export type IconName =
  | "maximize" | "restore" | "popout" | "collapse" | "expand" | "close"
  | "plus" | "minus" | "fit" | "undo" | "redo" | "check";

const PATHS: Record<IconName, string> = {
  maximize: "M3 7V3h4M13 3h4v4M17 13v4h-4M7 17H3v-4",
  restore: "M7 3v4H3M17 7h-4V3M13 17v-4h4M3 13h4v4",
  popout: "M11 3h6v6M17 3l-8 8M14 12v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4",
  collapse: "M5 12.5 10 7.5l5 5",
  expand: "M5 7.5l5 5 5-5",
  close: "M5 5l10 10M15 5 5 15",
  plus: "M10 4v12M4 10h12",
  minus: "M4 10h12",
  fit: "M3 7V3h4M13 3h4v4M17 13v4h-4M7 17H3v-4M7 7h6v6H7z",
  undo: "M7 5 3 9l4 4M3 9h9a5 5 0 0 1 0 10h-2",
  redo: "M13 5l4 4-4 4M17 9H8a5 5 0 0 0 0 10h2",
  check: "M4 10.5l4 4 8-9",
};

export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
