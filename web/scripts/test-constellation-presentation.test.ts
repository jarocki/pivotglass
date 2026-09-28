import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { COVERAGE_LABELS, indicatorTypeLabel, reportedCountry, tooltipPosition } from "../app/constellation-presentation.ts";

test("rendered coverage marks use distinct familiar shapes with accessible labels", () => {
  const code = ts.transpileModule(readFileSync(new URL("../app/lite-brite-peg.tsx", import.meta.url), "utf8"), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const exports = {} as { LiteBritePeg: (props: { status: string; label: string; compact: boolean }) => ReturnType<typeof createElement> };
  runInNewContext(code, { exports, require: createRequire(import.meta.url) });
  const marks = Object.entries(COVERAGE_LABELS).map(([status, label]) => {
    const html = renderToStaticMarkup(createElement(exports.LiteBritePeg, { status, label, compact: true }));
    assert.ok(html.includes(`aria-label="${label}"`));
    assert.ok(html.includes('role="img"'));
    assert.doesNotMatch(html, /gradient|starburst|peg-outer/);
    return html.slice(html.indexOf("<svg"));
  });
  assert.equal(new Set(marks).size, 4);
});

test("status icons and small text have accessible contrast in every day and night theme", () => {
  const source = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  const luminance = (hex: string) => {
    const values = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    return values[0] * .2126 + values[1] * .7152 + values[2] * .0722;
  };
  const contrast = (a: string, b: string) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + .05) / (lo + .05);
  };
  for (const mode of ["DAY", "NIGHT"]) {
    const palette = source.split(`const ${mode}_PALETTES`)[1].split("\n};")[0];
    const rows = [...palette.matchAll(/(\w+): \{([^}]+)\}/g)];
    assert.equal(rows.length, 7);
    for (const [, name, values] of rows) {
      const color = (key: string) => values.match(new RegExp(`${key}: "(#[0-9a-f]{6})"`))![1];
      for (const background of [color("surface"), color("elevated")]) {
        for (const ink of [color("text_color"), color("dim_color")]) {
          assert.ok(contrast(ink, background) >= 4.5, `${mode} ${name}: text contrast`);
        }
        for (const ink of mode === "DAY" ? ["#176341", "#825600"] : ["#78dfac", "#f1c66d"]) {
          assert.ok(contrast(ink, background) >= 3, `${mode} ${name}: icon contrast`);
        }
      }
    }
  }
});

test("coverage labels distinguish absent evidence from unavailable automation", () => {
  assert.equal(COVERAGE_LABELS.empty, "No evidence");
  assert.equal(COVERAGE_LABELS.deferred, "No automated path");
  assert.equal(COVERAGE_LABELS.filled, "Coverage met");
  assert.equal(new Set(Object.values(COVERAGE_LABELS)).size, 4);
  assert.doesNotMatch(Object.values(COVERAGE_LABELS).join(" "), /safe|malicious|confidence|queued/i);
});

test("indicator labels and country flags are recognizable without inventing geography", () => {
  assert.equal(indicatorTypeLabel("ipv6-addr"), "IPv6");
  assert.equal(indicatorTypeLabel("domain-name"), "Domain");
  assert.deepEqual(reportedCountry("DE"), { name: "Germany", flag: "🇩🇪", code: "DE" });
  for (const invalid of [null, undefined, "", "ZZ", "XX", "EU", "UN", "us", "<script>", ["US"]]) {
    assert.equal(reportedCountry(invalid), null);
  }
});

test("measured tooltip flips and clamps at viewport edges, including narrow views", () => {
  assert.deepEqual(tooltipPosition({ left: 950, top: 640, bottom: 675 },
    { width: 360, height: 220 }, { width: 1024, height: 768 }), { left: 652, top: 412 });
  assert.deepEqual(tooltipPosition({ left: -20, top: 8, bottom: 30 },
    { width: 296, height: 250 }, { width: 320, height: 568 }), { left: 12, top: 38 });
  assert.deepEqual(tooltipPosition({ left: 20, top: 4, bottom: 22 },
    { width: 296, height: 544 }, { width: 320, height: 568 }), { left: 12, top: 12 });
});
