"use client";

import { CSSProperties } from "react";

export type RGB = readonly [red: number, green: number, blue: number];

const STATUS_RGB: Readonly<Record<string, RGB>> = {
  planned: [24, 24, 24],
  queued: [192, 128, 0],
  running: [0, 128, 255],
  succeeded: [0, 255, 0],
  filled: [0, 255, 0],
  partial: [128, 128, 128],
  deferred: [32, 32, 32],
  empty: [0, 0, 0],
  failed: [255, 0, 0],
  skipped: [128, 96, 0],
  cancelled: [128, 0, 0],
};

const clamp8 = (value: number) => Math.max(0, Math.min(255, Math.round(value)));

export function rgbForStatus(status: string): RGB {
  return STATUS_RGB[status] ?? STATUS_RGB.planned;
}

export function rgbLabelForStatus(status: string): string {
  return rgbForStatus(status).join(", ");
}

export function RGBLed({
  rgb,
  status,
  label,
}: {
  rgb?: RGB;
  status?: string;
  label?: string;
}) {
  const [red, green, blue] = (rgb ?? rgbForStatus(status ?? "planned")).map(clamp8) as [number, number, number];
  const style = {
    "--led-r": red,
    "--led-g": green,
    "--led-b": blue,
    "--led-color": `rgb(${red} ${green} ${blue})`,
  } as CSSProperties;
  return (
    <span
      className="rgb-led"
      style={style}
      data-rgb={`${red},${green},${blue}`}
      aria-label={label ?? `RGB ${red}, ${green}, ${blue}`}
      role="img"
    >
      <i className="rgb-led-red" aria-hidden="true" />
      <i className="rgb-led-green" aria-hidden="true" />
      <i className="rgb-led-blue" aria-hidden="true" />
    </span>
  );
}
