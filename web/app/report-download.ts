/** Prepare a portable download from the generated Markdown, without rendering it. */
export function reportMarkdownDownload(text: string, workspace: string, version: string) {
  const safeWorkspace = workspace.normalize("NFKC").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64) || "workspace";
  const safeVersion = version.replace(/[^a-zA-Z0-9.-]/g, "").slice(0, 32) || "unknown";
  return { content: text, mime: "text/markdown;charset=utf-8", filename: `pivotglass-${safeWorkspace}-v${safeVersion}-report.md` };
}

/** Browser boundary used by the report action. The injected form supports contract tests. */
export type ReportDownloadBrowser = {
  createObjectURL(blob: Blob): string;
  revokeObjectURL(url: string): void;
  createAnchor(): { href: string; download: string; click(): void; remove(): void };
  appendAnchor(anchor: ReturnType<ReportDownloadBrowser["createAnchor"]>): void;
  scheduleCleanup(callback: () => void, milliseconds: number): void;
};

export function saveReportMarkdown(text: string, workspace: string, version: string, browser?: ReportDownloadBrowser): void {
  const boundary: ReportDownloadBrowser = browser ?? {
    createObjectURL: (blob) => URL.createObjectURL(blob),
    revokeObjectURL: (url) => URL.revokeObjectURL(url),
    createAnchor: () => document.createElement("a"),
    appendAnchor: (anchor) => document.body.appendChild(anchor as HTMLAnchorElement),
    scheduleCleanup: (callback, milliseconds) => { window.setTimeout(callback, milliseconds); },
  };
  const download = reportMarkdownDownload(text, workspace, version);
  const url = boundary.createObjectURL(new Blob([download.content], { type: download.mime }));
  const anchor = boundary.createAnchor();
  anchor.href = url;
  anchor.download = download.filename;
  try {
    boundary.appendAnchor(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    boundary.scheduleCleanup(() => boundary.revokeObjectURL(url), 1000);
  }
}
