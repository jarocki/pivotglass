import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import * as review from "../app/intake-review.ts";

type Element = { type: any; props: Record<string, any> };
/** Stand-in for the focus view: the harness inspects its props, it is never rendered. */
function IndicatorFocus() { return null; }
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
  class FakeFile { content: string; name: string; type: string; size: number;
    constructor(parts: string[], name: string, options: { type: string }) { this.content = parts.join(""); this.name = name; this.type = options.type; this.size = this.content.length; } }
  const local: Record<string, unknown> = { react, "./intake-review": review, "./indicator-focus": { IndicatorFocus } };
  runInNewContext(code, { exports, require: (name: string) => local[name] ?? require(name), fetch: fetcher, FileReader, File: FakeFile });
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
  await button(view, "Retry").props.onClick(); await app.settle();
  view = app.render();
  assert.match(text(view), /active workspace changed/);
  mode = "ok";
  await button(view, "Retry").props.onClick(); await app.settle();
  assert.match(text(app.render()), /No documents have been ingested/);
});

const focusOf = (view: Element) => nodes(view).find((node) => node.type === IndicatorFocus);

test("choosing a file previews straight into focus mode; admitting stores the source with exactly the chosen keys", async () => {
  const candidates = Array.from({ length: 125 }, (_, index) => ({
    id: String(index), selection_key: `key-${index}`, normalized_value: `host-${index}.example`, raw_value: `host-${index}.example`,
    entity_type: "domain-name", start_char: index * 20, end_char: index * 20 + 14, start_line: index + 1,
  }));
  const submitted: any[] = [];
  const app = harness(async (url, options) => {
    if (url === "/api/documents") return response({ workspace: "case-a", documents: [] });
    if (url.endsWith("/preview")) return response({ filename: "list.txt", content_sha256: "abc", detected_media_type: "text/plain", state: "parsed", warnings: [], errors: [], skipped: [], output_text: "preview",
      rendering: { kind: "text", anchoring: "exact", html: null, notes: [] }, entity_extraction: { candidates, candidate_count: 125, warnings: [], relations: {} } });
    submitted.push({ url, body: JSON.parse(options.body) });
    if (url === "/api/documents/ingest") return response({ receipt: { candidate_count: 125, intake: { occurrence_id: "occ-9" } }, candidate_admission: { admitted_candidate_count: 2, entity_count: 2, new_entity_count: 2 }, library: [] });
    assert.equal(url, "/api/documents/candidates/admit");
    return response({ admitted: true, receipt: { admitted_candidate_count: 1, entity_count: 1, new_entity_count: 0 } });
  });
  let view = app.render(); await app.settle();
  assert.equal(focusOf(app.render()), undefined, "nothing opens before a source is chosen");
  nodes(view).find((node) => node.type === "input" && node.props.type === "file")!.props.onChange({ target: { files: [{ name: "list.txt", size: 100, content: "preview" }], value: "" } });
  await app.settle(); view = app.render();
  const focus = focusOf(view)!;
  assert.ok(focus, "preview opens focus mode without another click");
  assert.equal(focus.props.source.stored, false);
  assert.equal(focus.props.source.candidates.length, 125, "every candidate is reviewable");
  assert.match(text(view), /previewed locally · not stored/);
  assert.equal(submitted.length, 0, "preview alone stores nothing");

  await focus.props.onAdmit(["key-0", "key-100"]); await app.settle(); view = app.render();
  assert.equal(submitted[0].url, "/api/documents/ingest");
  assert.deepEqual(submitted[0].body.candidate_keys, ["key-0", "key-100"]);
  assert.equal(submitted[0].body.expected_workspace, "case-a");
  assert.equal(submitted[0].body.expected_sha256, "abc");
  assert.equal(focusOf(view)!.props.source.occurrenceId, "occ-9");
  assert.deepEqual([...focusOf(view)!.props.admittedKeys], ["key-0", "key-100"]);

  // A second admission from the same source must not store it twice.
  await focusOf(view)!.props.onAdmit(["key-7"]); await app.settle(); view = app.render();
  assert.equal(submitted[1].url, "/api/documents/candidates/admit");
  assert.equal(submitted[1].body.occurrence_id, "occ-9");
  assert.deepEqual(submitted[1].body.candidate_keys, ["key-7"]);

  focusOf(view)!.props.onClose(); view = app.render();
  assert.deepEqual(nodes(view).filter((node) => node.props["data-action"] === "use-admitted-indicator").map(text), ["host-0.example", "host-100.example", "host-7.example"]);
  button(view, "host-100.example").props.onClick();
  assert.deepEqual(app.used, ["host-100.example"], "investigation is only prepared, never run from intake");
});

test("pasted text becomes a reviewable source without making a file", async () => {
  const seen: any[] = [];
  const app = harness(async (url, options) => {
    if (url === "/api/documents") return response({ workspace: "case-a", documents: [] });
    seen.push(JSON.parse(options.body));
    return response({ filename: seen[0].filename, content_sha256: "p", detected_media_type: "text/plain", state: "parsed", warnings: [], errors: [], skipped: [], output_text: "203.0.113.7", entity_extraction: { candidates: [], candidate_count: 0, warnings: [] } });
  });
  let view = app.render(); await app.settle();
  button(view, "Paste text").props.onClick(); view = app.render();
  nodes(view).find((node) => node.type === "textarea")!.props.onChange({ target: { value: "C2 203.0.113.7" } }); view = app.render();
  button(view, "Review ⌘↵").props.onClick(); await app.settle(); view = app.render();
  assert.match(seen[0].filename, /^pasted-\d{12}\.txt$/);
  assert.equal(Buffer.from(seen[0].content_base64, "base64").toString(), "C2 203.0.113.7");
  assert.ok(focusOf(view));
});

test("late library responses are ignored after the intake workspace unmounts", async () => {
  let resolve: (value: ResponseData) => void = () => {};
  const app = harness(() => new Promise((done) => { resolve = done; }));
  app.render(); await app.settle(); app.unmount();
  resolve(response({ workspace: "case-a", documents: [] })); await app.settle();
  assert.doesNotMatch(text(app.render()), /No documents have been ingested/);
});

test("stored sources reopen in focus mode with the hash on demand, prior admissions, and stored-source admission", async () => {
  const fullHash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
  const candidates = [
    { id: "stored-1", selection_key: "stored-key-1", normalized_value: "stored.example", raw_value: "stored.example", entity_type: "domain-name", start_line: 4, start_char: 10, end_char: 24, state: "candidate" },
    { id: "stored-2", selection_key: "stored-key-2", normalized_value: "203.0.113.7", raw_value: "203.0.113.7", entity_type: "ipv4-addr", start_line: 5, start_char: 30, end_char: 41, state: "admitted" }];
  let admitted: any;
  const app = harness(async (url, options) => {
    if (url === "/api/documents") return response({ workspace: "case-a", documents: [{ occurrence_id: "occ-1", filename: "report.pdf", source_kind: "local", detected_media_type: "application/pdf", size_bytes: 42, content_sha256: fullHash, parser_state: "parsed", candidate_count: 2, acquired_at: "2026-09-23T00:00:00Z" }] });
    if (url === "/api/documents/occ-1") return response({ occurrence_id: "occ-1", filename: "report.pdf", content_sha256: fullHash, detected_media_type: "application/pdf", parser: { state: "parsed", output_text: "[page 1]", warnings: [], errors: [], skipped: [] }, candidates, rendering: { kind: "pdf", anchoring: "ordinal", html: null, notes: [] }, relations: {} });
    assert.equal(url, "/api/documents/candidates/admit");
    admitted = JSON.parse(options.body);
    return response({ admitted: true, receipt: { admitted_candidate_count: 1, entity_count: 1, new_entity_count: 1 } });
  });
  app.render(); await app.settle();
  let view = app.render();
  // The row shows a short, comparable form; the full digest stays one hover away.
  assert.match(text(view), new RegExp(`${fullHash.slice(0, 8)}…${fullHash.slice(-8)}`));
  assert.ok(nodes(view).some((node: any) => node.props?.title === `SHA-256 ${fullHash}`));
  await nodes(view).find((node) => node.props["data-action"] === "open-stored-source")!.props.onClick(); await app.settle();
  view = app.render();
  const focus = focusOf(view)!;
  assert.equal(focus.props.source.stored, true);
  assert.equal(focus.props.source.rendering.kind, "pdf");
  assert.deepEqual([...focus.props.admittedKeys], ["stored-key-2"]);
  await focus.props.onAdmit(["stored-key-1"]); await app.settle();
  assert.equal(admitted.occurrence_id, "occ-1");
  assert.deepEqual(admitted.candidate_keys, ["stored-key-1"]);
  assert.equal(admitted.expected_workspace, "case-a");
});
