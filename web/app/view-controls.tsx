"use client";

import { DENSITIES, TEXT_SIZES, WIDTHS, type ViewPreferences } from "./view-preferences";

function Segmented<T extends string>({ label, options, value, onChange }: {
  label: string; options: Array<{ value: T; label: string }>; value: T; onChange: (value: T) => void;
}) {
  return <div className="view-row" role="group" aria-label={label}>
    <span>{label}</span>
    <div className="segmented">{options.map((option) => <button type="button" key={option.value}
      className={value === option.value ? "selected" : ""} aria-pressed={value === option.value}
      onClick={() => onChange(option.value)}>{option.label}</button>)}</div>
  </div>;
}

/** The only control surface for view preferences; keyboard: \ width, + / − text size. */
export function ViewControls({ value, onChange, onQuiet }: {
  value: ViewPreferences;
  onChange: (value: ViewPreferences) => void;
  onQuiet: () => void;
}) {
  return <fieldset className="view-controls">
    <legend>View</legend>
    <Segmented label="Width" options={WIDTHS} value={value.width} onChange={(width) => onChange({ ...value, width })}/>
    <Segmented label="Text" options={TEXT_SIZES} value={value.text} onChange={(text) => onChange({ ...value, text })}/>
    <Segmented label="Density" options={DENSITIES} value={value.density} onChange={(density) => onChange({ ...value, density })}/>
    <label className="view-spotlight"><input type="checkbox" checked={value.spotlight}
      onChange={(event) => onChange({ ...value, spotlight: event.target.checked })} />
      Dim other panes while I work</label>
    <button type="button" onClick={onQuiet}>Quiet workspace</button>
    <small>Turns off motion, music, voice, and unsolicited advice. <kbd>\</kbd> cycles width · <kbd>+</kbd> <kbd>−</kbd> text size · <kbd>z</kbd> maximize · <kbd>Shift</kbd>+<kbd>Z</kbd> pop out.</small>
  </fieldset>;
}
