import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import * as review from "../app/intake-review.ts";

type Element = { type: string; props: Record<string, any> };
type ResponseData = { ok: boolean; json: () => Promise<any> };
const response = (data: any, ok = true): ResponseData => ({ ok, json: async () => data });
const code = ts.transpileModule(readFileSync(new URL("../app/document-intake.tsx", import.meta.url), "utf8"), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

/** Exercises real component event handlers with deterministic hook state and API responses. */
function harness(fetcher: (url: string, options?: any) => Promise<ResponseData>) {
  const state: any[] = [];
  const cleanups: Array<() => void> = [];
  const effects: Array<() => (() => void) | void> = [];
  let cursor = 0;
  const react = {
    useState(initial: any) {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], (value: any) => { state[index] = typeof value === "function" ? value(state[index]) : value; }];
    },
    useRef(initial: any) {
      const index = cursor++;
      if (!(index in state)) state[index] = { current: initial };
      return state[index];
    },
    useCallback(callback: any, deps: any[]) {
      const index = cursor++;
      if (!state[index] || deps.some((dep, i) => dep !== state[index].deps[i])) state[index] = { callback, deps };
      return state[index].callback;
    },
    useEffect(effect: () => void, deps: any[]) {
      const index = cursor++;
      if (!state[index] || deps.some((dep, i) => dep !== state[index][i])) { state[index] = deps; effects.push(effect); }
    },
  };
  const require = createRequire(import.meta.url);
  const exports: any = {};
  class FileReader {
    result = "";
    onload?: () => void;
    readAsDataURL(file: any) { this.result = `data:text/plain;base64,${Buffer.from(file.content).toString("base64")}`; this.onload?.(); }
  }
  runInNewContext(code, { exports, require: (name: string) => name === "react" ? react : name === "./intake-review" ? review : require(name), fetch: fetcher, FileReader });
  const used: string[] = [];
  return {
    used,
    render: () => { cursor = 0; return exports.DocumentIntake({ workspace: "case-a", onUseIndicator: (value: string) => used.push(value) }) as Element; },
    async settle() { for (const effect of effects.splice(0)) { const cleanup = effect(); if (cleanup) cleanups.push(cleanup); } await new Promise(setImmediate); },
    unmount: () => cleanups.forEach((cleanup) => cleanup()),
  };
}

function nodes(root: any): Element[] {
  if (Array.isArray(root)) return root.flatMap(nodes);
  if (!root || typeof root !== "object" || !root.props) return [];
  return [root, ...nodes(root.props.children)];
}
function text(root: any): string {
  if (Array.isArray(root)) return root.map(text).join("");
  if (root == null || typeof root === "boolean") return "";
  if (typeof root === "object") return text(root.props?.children);
  return String(root);
}
function button(root: Element, label: string): Element {
  const found = nodes(root).find((node) => node.type === "button" && text(node) === label);
  assert.ok(found, `button ${label} exists`);
  return found;
}

test("library failure is not an empty library, retry restores records, and workspace mismatch is rejected", async () => {
  let mode = "fail";
  const app = harness(async () => mode === "fail" ? response({ error: "Temporary outage" }, false)
    : response({ workspace: mode === "mismatch" ? "case-b" : "case-a", documents: [] }));
  assert.match(text(app.render()), /Loading the document library/);
  app.render(); await app.settle();
  let view = app.render();
  assert.match(text(view), /Temporary outage/);
  assert.doesNotMatch(text(view), /No documents have been ingested/);
  mode = "mismatch";
  await button(view, "RETRY LIBRARY").props.onClick(); await app.settle();
  view = app.render();
  assert.match(text(view), /active workspace changed/);
  mode = "ok";
  await button(view, "RETRY LIBRARY").props.onClick(); await app.settle();
  assert.match(text(app.render()), /No documents have been ingested/);
});

test("reviewing later pages preserves explicit selection and successful Use prepares only the selected indicator", async () => {
  const candidates = Array.from({ length: 125 }, (_, index) => ({
    id: String(index), selection_key: `key-${index}`, normalized_value: `host-${index}.example`, raw_value: `host-${index}.example`, entity_type: "domain-name",
  }));
  let submitted: any;
  const app = harness(async (url, options) => {
    if (url === "/api/documents") return response({ workspace: "case-a", documents: [] });
    if (url.endsWith("/preview")) return response({ filename: "list.txt", content_sha256: "abc", state: "parsed", warnings: [], errors: [], skipped: [], output_text: "preview", entity_extraction: { candidates, candidate_count: 125, warnings: [] } });
    assert.equal(url, "/api/documents/ingest");
    submitted = JSON.parse(options.body);
    return response({ receipt: { candidate_count: 125 }, candidate_admission: { admitted_candidate_count: 2, entity_count: 2, new_entity_count: 2 }, library: [] });
  });
  let view = app.render(); await app.settle();
  nodes(view).find((node) => node.type === "input" && node.props.type === "file")!.props.onChange({ target: { files: [{ name: "list.txt", size: 100, content: "preview" }] } });
  view = app.render();
  await button(view, "PREVIEW LOCALLY").props.onClick(); await app.settle(); view = app.render();
  nodes(view).find((node) => node.props.type === "checkbox")!.props.onChange({ target: { checked: true } });
  button(view, "NEXT").props.onClick(); view = app.render();
  button(view, "NEXT").props.onClick(); view = app.render();
  assert.match(text(view), /101–125 of 125/);
  nodes(view).find((node) => node.props.type === "checkbox")!.props.onChange({ target: { checked: true } });
  view = app.render();
  await button(view, "INGEST SOURCE + ADD 2 ENTITIES").props.onClick(); await app.settle(); view = app.render();
  assert.deepEqual(submitted.candidate_keys, ["key-0", "key-100"]);
  assert.equal(submitted.expected_workspace, "case-a");
  assert.deepEqual(nodes(view).filter((node) => node.props["data-action"] === "use-admitted-indicator").map(text), ["Use host-0.example", "Use host-100.example"]);
  button(view, "Use host-100.example").props.onClick();
  assert.deepEqual(app.used, ["host-100.example"]);
  assert.equal(nodes(view).find((node) => node.props.type === "checkbox")!.props.disabled, true);
  nodes(view).find((node) => node.props.type === "file")!.props.onChange({ target: { files: [{ name: "new.txt", size: 10, content: "new" }] } });
  assert.doesNotMatch(text(app.render()), /Use host-|INGESTED/);
});

test("late library responses are ignored after the intake workspace unmounts", async () => {
  let resolve: (value: ResponseData) => void = () => {};
  const app = harness(() => new Promise((done) => { resolve = done; }));
  app.render(); await app.settle(); app.unmount();
  resolve(response({ workspace: "case-a", documents: [] })); await app.settle();
  assert.doesNotMatch(text(app.render()), /No documents have been ingested/);
});

test("stored library records can be reviewed again with the complete hash and candidates admitted", async () => {
  const fullHash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
  const detailCandidate = { id: "stored-1", selection_key: "stored-key-1", normalized_value: "stored.example", raw_value: "stored.example", entity_type: "domain-name", start_line: 4, start_column: 2, start_char: 10, end_char: 24 };
  let admitted: any;
  const app = harness(async (url, options) => {
    if (url === "/api/documents") return response({ workspace: "case-a", documents: [{ occurrence_id: "occ-1", filename: "report.json", source_kind: "upload", detected_media_type: "application/json", size_bytes: 42, content_sha256: fullHash, parser_state: "parsed", candidate_count: 1, acquired_at: "2026-09-23T00:00:00Z", operator: "local analyst", reused_content: false }] });
    if (url === "/api/documents/occ-1") return response({ occurrence_id: "occ-1", filename: "report.json", content_sha256: fullHash, size_bytes: 42, detected_media_type: "application/json", acquired_at: "2026-09-23T00:00:00Z", parser: { state: "parsed", output_text: "stored.example", warnings: [], errors: [], skipped: [] }, candidates: [detailCandidate], truth_boundary: "Stored source content is provenance." });
    assert.equal(url, "/api/documents/candidates/admit");
    admitted = JSON.parse(options.body);
    return response({ admitted: true, receipt: { admitted_candidate_count: 1, entity_count: 1, new_entity_count: 1 } });
  });
  app.render(); await app.settle();
  let view = app.render();
  assert.match(text(view), new RegExp(fullHash));
  await button(view, "REVIEW STORED SOURCE").props.onClick(); await app.settle();
  view = app.render();
  assert.match(text(view), /STORED SOURCE REVIEW/);
  assert.match(text(view), new RegExp(fullHash));
  nodes(view).find((node) => node.props.type === "checkbox" && node.props["aria-label"]?.includes("stored.example"))!.props.onChange({ target: { checked: true } });
  view = app.render();
  await button(view, "ADMIT SELECTED CANDIDATES").props.onClick(); await app.settle();
  assert.equal(admitted.occurrence_id, "occ-1");
  assert.deepEqual(admitted.candidate_keys, ["stored-key-1"]);
  assert.equal(admitted.expected_workspace, "case-a");
});
