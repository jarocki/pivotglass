import test from "node:test";
import assert from "node:assert/strict";
import { reportMarkdownDownload } from "../app/report-download.ts";

test("Markdown download preserves all generated text including Unicode and formatting", async () => {
  const markdown = "# Case café\n\n| Evidence | Value |\n|---|---|\n| file | invoice\\|viewer.bin |\n\n**Uncertain**: α ≠ β.\n";
  const result = reportMarkdownDownload(markdown, "training-case", "0.9.9");
  assert.equal(result.content, markdown);
  assert.equal(result.filename, "pivotglass-training-case-v0.9.9-report.md");
  assert.equal(result.mime, "text/markdown;charset=utf-8");
  assert.equal(await new Blob([result.content], { type: result.mime }).text(), markdown);
});

test("Filename cannot contain traversal, markup, control characters, or unbounded workspace text", () => {
  for (const workspace of ["../../private/secret", "<script>\n\u0000", "", " ", "a".repeat(1000)]) {
    const result = reportMarkdownDownload("source text", workspace, "0.9.9");
    assert.match(result.filename, /^pivotglass-[a-zA-Z0-9_-]+-v0\.9\.9-report\.md$/);
    assert.ok(result.filename.length < 110);
    assert.equal(result.content, "source text");
  }
});

test("report download attaches and clicks an anchor carrying the exact UTF8 Blob, then releases it", async () => {
  const { saveReportMarkdown } = await import("../app/report-download.ts");
  const markdown = "# Actual report\n\nUnicode café and **formatting**.\n";
  const events: string[] = [];
  let emitted: Blob | undefined;
  let cleanup: (() => void) | undefined;
  const anchor = { href: "", download: "", click() { events.push("click"); assert.equal(anchor.href, "blob:report"); assert.equal(anchor.download, "pivotglass-captured-case-v0.9.9-report.md"); }, remove() { events.push("remove"); } };
  saveReportMarkdown(markdown, "captured-case", "0.9.9", {
    createObjectURL(blob) { emitted = blob; events.push("blob"); return "blob:report"; },
    revokeObjectURL(url) { assert.equal(url, "blob:report"); events.push("revoke"); },
    createAnchor() { events.push("anchor"); return anchor; },
    appendAnchor(value) { assert.equal(value, anchor); events.push("attach"); },
    scheduleCleanup(callback, milliseconds) { assert.equal(milliseconds, 1000); cleanup = callback; events.push("schedule"); },
  });
  assert.ok(emitted);
  assert.equal(emitted.type, "text/markdown;charset=utf-8");
  assert.equal(await emitted.text(), markdown);
  assert.deepEqual(events, ["blob", "anchor", "attach", "click", "remove", "schedule"]);
  assert.ok(cleanup); cleanup();
  assert.equal(events.at(-1), "revoke");
});

test("failed browser anchor click releases resources instead of leaking report URLs", async () => {
  const { saveReportMarkdown } = await import("../app/report-download.ts");
  let removed = false;
  let revoked = false;
  assert.throws(() => saveReportMarkdown("# report", "case", "0.9.9", {
    createObjectURL() { return "blob:failed"; },
    revokeObjectURL() { revoked = true; },
    createAnchor() { return { href: "", download: "", click() { throw new Error("browser refused download"); }, remove() { removed = true; } }; },
    appendAnchor() {},
    scheduleCleanup(callback) { callback(); },
  }), /browser refused download/);
  assert.equal(removed, true);
  assert.equal(revoked, true);
});
