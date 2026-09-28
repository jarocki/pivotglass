"use client";

import { useId } from "react";
import type { ReadingPreferences } from "./reading-preferences";

export function ReadingControls({ value, onChange, onQuiet }: {
  value: ReadingPreferences;
  onChange: (value: ReadingPreferences) => void;
  onQuiet: () => void;
}) {
  const id = useId();
  return <fieldset className="reading-controls">
    <legend>Reading & attention</legend>
    <label htmlFor={`${id}-size`}>Text size</label>
    <select id={`${id}-size`} value={value.textSize}
      onChange={(event) => onChange({ ...value, textSize: event.target.value === "large" ? "large" : "standard" })}>
      <option value="standard">Standard — compact data</option>
      <option value="large">Larger — easier reading</option>
    </select>
    <label className="reading-spotlight"><input type="checkbox" checked={value.spotlight}
      onChange={(event) => onChange({ ...value, spotlight: event.target.checked })} />
      Dim other panels while I work</label>
    <small>Optional spotlight works with full visual effects. Walkthrough highlighting is separate and can be dismissed.</small>
    <button type="button" onClick={onQuiet}>Quiet workspace</button>
    <small>Turns off decorative motion, music, voice, unsolicited character advice, and hover dimming. Work, alerts, and Help remain available. Restore each option here or in More.</small>
  </fieldset>;
}
