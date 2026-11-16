"use client";

/*
 * Source intake (#17). One step from source to review: choose, drop, or paste,
 * and the preview opens directly in indicator focus mode. Admission from focus
 * mode stores the source and admits the selected indicators in one request.
 * Preview alone stores nothing; enrichment never runs from intake.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { createIntakeRequestScope } from "./intake-review";
import { IndicatorFocus, type FocusSource } from "./indicator-focus";
import type { DocumentRelations, FocusCandidate } from "./focus-model";

type Rendering = FocusSource["rendering"];

type DocumentPreview = {
  content_sha256: string;
  filename: string;
  size_bytes: number;
  detected_media_type: string;
  state: "parsed" | "partial" | "failed";
  output_text: string;
  warnings: string[];
  errors: string[];
  skipped: string[];
  rendering?: Rendering;
  entity_extraction: {
    candidate_count: number;
    warnings: string[];
    candidates: FocusCandidate[];
    relations?: DocumentRelations;
  };
};

type DocumentLibraryRecord = {
  occurrence_id: string;
  filename: string;
  source_kind: string;
  detected_media_type: string;
  size_bytes: number;
  content_sha256: string;
  parser_state: string;
  candidate_count: number;
  acquired_at: string;
};

type StoredDocumentDetail = {
  occurrence_id: string;
  filename: string;
  content_sha256: string;
  detected_media_type: string;
  parser: { state: string; output_text: string; warnings: string[]; errors: string[]; skipped: string[] };
  candidates: FocusCandidate[];
  rendering?: Rendering;
  relations?: DocumentRelations;
};

type AdmissionCounts = { admitted_candidate_count: number; entity_count: number; new_entity_count: number };

type IngestResult = {
  receipt: { candidate_count: number; intake: { occurrence_id: string } };
  candidate_admission?: AdmissionCounts | null;
  candidate_admission_error?: string | null;
  library: DocumentLibraryRecord[];
};

type Pending = { file: File; base64: string; preview: DocumentPreview; occurrenceId: string | null };

export type IntakeWorkflowEvent =
  | "intake_opened"
  | "file_selected"
  | "preview_complete"
  | "source_ingested"
  | "entities_admitted";

const MAX_BYTES = 10 * 1024 * 1024;
const TEXT_RENDERING: Rendering = { kind: "text", anchoring: "exact", html: null, notes: [] };

function asBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The browser could not read this file."));
    reader.onload = () => {
      const url = String(reader.result ?? "");
      const marker = url.indexOf(",");
      if (marker < 0) reject(new Error("The browser did not produce a readable file."));
      else resolve(url.slice(marker + 1));
    };
    reader.readAsDataURL(file);
  });
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

export function DocumentIntake({
  workspace,
  onChanged,
  onWorkflowEvent,
  onUseIndicator,
}: {
  workspace: string;
  onChanged?: () => Promise<void> | void;
  onWorkflowEvent?: (event: IntakeWorkflowEvent) => void;
  onUseIndicator?: (value: string) => void;
}) {
  const [library, setLibrary] = useState<DocumentLibraryRecord[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState("");
  const [libraryFilter, setLibraryFilter] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [focus, setFocus] = useState<FocusSource | null>(null);
  const [admittedKeys, setAdmittedKeys] = useState<Set<string>>(new Set());
  const [admittedValues, setAdmittedValues] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [dragging, setDragging] = useState(false);
  const alive = useRef(true);
  const libraryRequests = useRef(createIntakeRequestScope());
  const fileInput = useRef<HTMLInputElement>(null);

  const loadLibrary = useCallback(async () => {
    const ticket = libraryRequests.current.begin();
    setLibraryLoading(true);
    setLibraryError("");
    try {
      const response = await fetch("/api/documents", { cache: "no-store" });
      const result = await response.json() as { workspace?: string; documents?: DocumentLibraryRecord[]; error?: string };
      if (!response.ok || result.error) throw new Error(result.error ?? "Document library could not be loaded.");
      if (result.workspace !== workspace) throw new Error("The active workspace changed. Refresh this page before adding documents.");
      if (!Array.isArray(result.documents)) throw new Error("The document library response was incomplete. Please retry.");
      if (alive.current && libraryRequests.current.current(ticket)) setLibrary(result.documents);
    } catch (reason) {
      if (alive.current && libraryRequests.current.current(ticket)) {
        setLibraryError(reason instanceof Error ? reason.message : "Document library could not be loaded.");
      }
    } finally {
      if (alive.current && libraryRequests.current.current(ticket)) setLibraryLoading(false);
    }
  }, [workspace]);

  useEffect(() => {
    alive.current = true;
    const requests = libraryRequests.current;
    void loadLibrary();
    return () => { alive.current = false; requests.invalidate(); };
  }, [loadLibrary]);

  const openPreview = async (file: File) => {
    if (file.size > MAX_BYTES) { setError("Sources are limited to 10 MiB."); return; }
    onWorkflowEvent?.("file_selected");
    setBusy(true); setError(""); setStatus(`Reading ${file.name}…`);
    setAdmittedKeys(new Set()); setAdmittedValues([]);
    try {
      const base64 = await asBase64(file);
      if (!alive.current) return;
      const response = await fetch("/api/documents/preview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: file.name, media_type: file.type || null, content_base64: base64 }),
      });
      const preview = await response.json() as DocumentPreview & { error?: string };
      if (!alive.current) return;
      if (!response.ok || preview.error) throw new Error(preview.error ?? "Document preview failed.");
      setPending({ file, base64, preview, occurrenceId: null });
      setStatus(`${preview.filename} previewed locally · not stored`);
      setFocus(previewSource(preview, file));
      onWorkflowEvent?.("preview_complete");
      onWorkflowEvent?.("intake_opened");
    } catch (reason) {
      if (alive.current) { setError(reason instanceof Error ? reason.message : "Document preview failed."); setStatus(""); }
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const recordAdmission = (counts: AdmissionCounts, keys: string[], source: FocusCandidate[]) => {
    const values = [...new Set(source.filter((item) => keys.includes(item.selection_key)).map((item) => item.normalized_value))];
    setAdmittedKeys((current) => new Set([...current, ...keys]));
    setAdmittedValues((current) => [...new Set([...current, ...values])]);
    setStatus(`Admitted ${plural(values.length, "indicator")} · ${counts.new_entity_count} new to this case`);
    onWorkflowEvent?.("entities_admitted");
  };

  /** Store an unstored preview, optionally admitting ``keys`` in the same request. */
  const ingest = async (keys: string[]) => {
    if (!pending) return;
    const response = await fetch("/api/documents/ingest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: pending.file.name, media_type: pending.file.type || null, content_base64: pending.base64,
        expected_sha256: pending.preview.content_sha256, operator: "local analyst",
        expected_workspace: workspace, candidate_keys: keys,
      }),
    });
    const result = await response.json() as IngestResult & { error?: string };
    if (!response.ok || result.error) throw new Error(result.error ?? "Document ingestion failed.");
    const occurrenceId = result.receipt.intake.occurrence_id;
    libraryRequests.current.invalidate();
    setLibraryLoading(false); setLibraryError("");
    setLibrary(result.library);
    setPending({ ...pending, occurrenceId });
    setFocus((current) => current && { ...current, stored: true, occurrenceId });
    if (result.candidate_admission) recordAdmission(result.candidate_admission, keys, pending.preview.entity_extraction.candidates);
    else setStatus(`${pending.preview.filename} stored`);
    if (result.candidate_admission_error) {
      setError(`Source stored, but admission did not complete: ${result.candidate_admission_error} Admit again to retry; the source will not be stored twice.`);
    }
    onWorkflowEvent?.(result.candidate_admission ? "entities_admitted" : "source_ingested");
    await onChanged?.();
  };

  const admitStored = async (occurrenceId: string, keys: string[], source: FocusCandidate[]) => {
    const response = await fetch("/api/documents/candidates/admit", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ occurrence_id: occurrenceId, candidate_keys: keys, operator: "local analyst", expected_workspace: workspace }),
    });
    const result = await response.json() as { receipt?: AdmissionCounts; error?: string };
    if (!response.ok || result.error || !result.receipt) throw new Error(result.error ?? "Selected indicators could not be admitted.");
    recordAdmission(result.receipt, keys, source);
    await loadLibrary();
    await onChanged?.();
  };

  const admit = async (keys: string[]) => {
    if (!focus) return;
    setBusy(true); setError("");
    try {
      if (focus.occurrenceId) await admitStored(focus.occurrenceId, keys, focus.candidates);
      else await ingest(keys);
    } catch (reason) {
      if (alive.current) setError(reason instanceof Error ? reason.message : "Admission did not complete.");
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const store = async () => {
    setBusy(true); setError("");
    try { await ingest([]); } catch (reason) {
      if (alive.current) setError(reason instanceof Error ? reason.message : "Document ingestion failed.");
    } finally { if (alive.current) setBusy(false); }
  };

  const openStored = async (item: DocumentLibraryRecord) => {
    setBusy(true); setError(""); setStatus(`Opening ${item.filename}…`);
    try {
      const response = await fetch(`/api/documents/${encodeURIComponent(item.occurrence_id)}`, { cache: "no-store" });
      const detail = await response.json() as StoredDocumentDetail & { error?: string };
      if (!response.ok || detail.error) throw new Error(detail.error ?? "Stored document could not be opened.");
      if (!alive.current) return;
      setPending(null);
      setAdmittedKeys(new Set(detail.candidates.filter((item) => item.state === "admitted").map((item) => item.selection_key)));
      setAdmittedValues([]);
      setStatus("");
      setFocus(storedSource(detail));
      onWorkflowEvent?.("intake_opened");
    } catch (reason) {
      if (alive.current) { setError(reason instanceof Error ? reason.message : "Stored document could not be opened."); setStatus(""); }
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const openPaste = () => {
    const text = pasteText.trim();
    if (!text) return;
    const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
    void openPreview(new File([text], `pasted-${stamp}.txt`, { type: "text/plain" }));
    setPasteOpen(false); setPasteText("");
  };

  const query = libraryFilter.trim().toLocaleLowerCase();
  const visibleLibrary = library
    .filter((item) => !query || `${item.filename} ${item.detected_media_type}`.toLocaleLowerCase().includes(query))
    .toSorted((left, right) => right.acquired_at.localeCompare(left.acquired_at));

  return (
    <section
      className={`document-intake ${dragging ? "dragging" : ""}`}
      aria-label="Add sources"
      onDragOver={(event) => { if (event.dataTransfer?.types.includes("Files")) { event.preventDefault(); setDragging(true); } }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); const file = event.dataTransfer?.files?.[0]; if (file) void openPreview(file); }}
      onPaste={(event) => {
        if ((event.target as HTMLElement).closest?.("textarea,input")) return;
        const file = event.clipboardData?.files?.[0];
        const text = event.clipboardData?.getData("text/plain");
        if (file) { event.preventDefault(); void openPreview(file); }
        else if (text?.trim()) { event.preventDefault(); setPasteText(text); setPasteOpen(true); }
      }}
    >
      <div className="intake-bar">
        <b>Sources</b>
        <button type="button" data-action="choose-source" disabled={busy} onClick={() => fileInput.current?.click()}>Open file…</button>
        <button type="button" disabled={busy} aria-expanded={pasteOpen} onClick={() => setPasteOpen((value) => !value)}>Paste text</button>
        <span className="intake-hint">or drop a report here</span>
        <input ref={fileInput} type="file" hidden disabled={busy}
          accept=".txt,.md,.html,.htm,.csv,.json,.jsonl,.ndjson,.eml,.pdf,text/*,application/json,application/pdf,message/rfc822"
          onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void openPreview(file); }}
          aria-label="Choose a source to review" />
        {status && <span className="intake-status" role="status">{status}</span>}
        {pending && !focus && <>
          <button type="button" data-action="reopen-focus" onClick={() => setFocus(previewSource(pending.preview, pending.file, pending.occurrenceId))}>Reopen</button>
          {!pending.occurrenceId && <button type="button" disabled={busy} onClick={() => void store()}>Store source</button>}
        </>}
      </div>
      {pasteOpen && <div className="intake-paste">
        <textarea autoFocus value={pasteText} onChange={(event) => setPasteText(event.target.value)} rows={5}
          placeholder="Paste report text or an indicator list" aria-label="Pasted source text"
          onKeyDown={(event) => { if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); openPaste(); } }} />
        <button type="button" disabled={!pasteText.trim() || busy} onClick={openPaste}>Review ⌘↵</button>
      </div>}
      {error && <p className="error" role="alert">{error}</p>}
      {admittedValues.length > 0 && onUseIndicator && !focus && (
        <div className="admitted-indicator-actions" aria-label="Investigate an admitted indicator">
          <span>Investigate:</span>
          {admittedValues.slice(0, 12).map((value) => <button type="button" key={value} data-action="use-admitted-indicator" onClick={() => onUseIndicator(value)}>{value}</button>)}
        </div>
      )}
      <details className="document-library" open={library.length > 0 && library.length <= 6}>
        <summary>Stored sources · {libraryLoading ? "loading" : library.length}</summary>
        {libraryLoading && <p role="status">Loading the document library for {workspace}…</p>}
        {libraryError && <div role="alert"><p>{libraryError}</p>{library.length > 0 && <small>Showing the last loaded list; it may be out of date.</small>}<button type="button" disabled={libraryLoading} onClick={() => void loadLibrary()}>RETRY LIBRARY</button></div>}
        {library.length > 6 && <input value={libraryFilter} onChange={(event) => setLibraryFilter(event.target.value)} placeholder="Filter sources" aria-label="Filter stored sources" />}
        {library.length ? <ol>
          {visibleLibrary.map((item) => <li key={item.occurrence_id}>
            <button type="button" className="library-open" disabled={busy} onClick={() => void openStored(item)} data-action="open-stored-source">
              <b title={item.filename}>{item.filename}</b>
              <span>{plural(item.candidate_count, "mention")} · {item.detected_media_type} · {new Date(item.acquired_at).toLocaleDateString()}</span>
            </button>
            <code className="document-hash" title="SHA-256 of the stored bytes">{item.content_sha256}</code>
          </li>)}
        </ol> : !libraryLoading && !libraryError ? <p>No documents have been ingested into this workspace.</p> : null}
      </details>
      {focus && <IndicatorFocus
        source={focus}
        workspace={workspace}
        admittedKeys={admittedKeys}
        busy={busy}
        status={[status, error].filter(Boolean).join(" · ")}
        onClose={() => { setFocus(null); setError(""); }}
        onAdmit={admit}
        onStore={focus.stored ? undefined : store}
        onInvestigate={onUseIndicator ? (value) => { setFocus(null); onUseIndicator(value); } : undefined}
      />}
    </section>
  );
}

function previewSource(preview: DocumentPreview, file: File, occurrenceId: string | null = null): FocusSource {
  return {
    id: `preview:${preview.content_sha256}`,
    filename: preview.filename,
    mediaType: preview.detected_media_type,
    outputText: preview.output_text,
    rendering: preview.rendering ?? TEXT_RENDERING,
    candidates: preview.entity_extraction.candidates,
    relations: preview.entity_extraction.relations ?? {},
    warnings: [...preview.warnings, ...preview.skipped, ...preview.errors, ...preview.entity_extraction.warnings],
    occurrenceId: occurrenceId ?? undefined,
    stored: Boolean(occurrenceId),
    loadPdf: () => file.arrayBuffer(),
  };
}

function storedSource(detail: StoredDocumentDetail): FocusSource {
  return {
    id: detail.occurrence_id,
    filename: detail.filename,
    mediaType: detail.detected_media_type,
    outputText: detail.parser.output_text,
    rendering: detail.rendering ?? TEXT_RENDERING,
    candidates: detail.candidates,
    relations: detail.relations ?? {},
    warnings: [...detail.parser.warnings, ...detail.parser.skipped, ...detail.parser.errors],
    occurrenceId: detail.occurrence_id,
    stored: true,
    loadPdf: async () => {
      const response = await fetch(`/api/documents/${encodeURIComponent(detail.occurrence_id)}/source`, { cache: "no-store" });
      if (!response.ok) throw new Error("Stored PDF bytes could not be loaded.");
      return response.arrayBuffer();
    },
  };
}
