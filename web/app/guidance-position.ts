export type RectLike = {
  top: number;
  right: number;
  bottom: number;
  left: number;
  width: number;
  height: number;
};

export type GuidancePlacement = {
  top: number;
  left: number;
  relation: "below" | "above" | "overlap";
};

export function placeGuidance(
  target: RectLike,
  panel: Pick<RectLike, "width" | "height">,
  viewport: { width: number; height: number },
  margin = 12,
  gap = 10,
): GuidancePlacement {
  const width = Math.min(panel.width || 420, Math.max(0, viewport.width - margin * 2));
  const height = Math.min(panel.height || 240, Math.max(0, viewport.height - margin * 2));
  const visibleTop = Math.max(margin, Math.min(target.top, viewport.height - margin));
  const visibleBottom = Math.max(margin, Math.min(target.bottom, viewport.height - margin));
  const below = visibleBottom + gap;
  const above = visibleTop - height - gap;
  const relation = below + height <= viewport.height - margin
    ? "below"
    : above >= margin
      ? "above"
      : "overlap";
  const rawTop = relation === "below" ? below : relation === "above" ? above : visibleTop;
  const top = Math.max(margin, Math.min(rawTop, viewport.height - height - margin));
  const centered = target.left + (target.width - width) / 2;
  const left = Math.max(margin, Math.min(centered, viewport.width - width - margin));
  return { top: Math.round(top), left: Math.round(left), relation };
}
