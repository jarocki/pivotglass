"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { candidatePage, createIntakeRequestScope, selectCandidatePage } from "./intake-review";

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
  truth_boundary: string;
  entity_extraction: {
    state: "complete" | "partial";
    warnings: string[];
    candidate_count: number;
    candidates: Array<{
      id: string;
      selection_key: string;
      entity_type: string;
      raw_value: string;
      normalized_value: string;
      start_char: number;
      end_char: number;
      start_byte: number;
      end_byte: number;
      start_line: number;
      start_column: number;
      end_line: number;
      end_column: number;
      rule_id: string;
      rule_version: string;
      normalization_note?: string | null;
    }>;
    truth_boundary: string;
  };
};

type DocumentLibraryRecord = {
  occurrence_id: string;
  filename: string;
  source_kind: string;
  source_uri?: string | null;
  detected_media_type: string;
  size_bytes: number;
  content_sha256: string;
  parser_state: string;
  candidate_count: number;
  acquired_at: string;
  operator: string;
  reused_content: boolean;
};

type StoredDocumentDetail = {
  occurrence_id: string;
  filename: string;
  content_sha256: string;
  size_bytes: number;
  detected_media_type: string;
  acquired_at: string;
  parser: {
    state: string;
    output_text: string;
    warnings: string[];
    errors: string[];
    skipped: string[];
  };
  candidates: Array<{
    id: string;
    selection_key: string;
    entity_type: string;
    raw_value: string;
    normalized_value: string;
    start_line: number;
    start_column: number;
    start_char: number;
    end_char: number;
    normalization_note?: string | null;
  }>;
  truth_boundary: string;
};

type AdmissionReceipt = {
  admitted: boolean;
  receipt: {
    candidate_count: number;
    truth_boundary: string;
    intake: { occurrence_id: string; reused_content: boolean };
  };
  candidate_admission?: {
    selected_count: number;
    admitted_candidate_count: number;
    already_admitted_count: number;
    entity_count: number;
    new_entity_count: number;
    truth_boundary: string;
  } | null;
  candidate_admission_error?: string | null;
  library: DocumentLibraryRecord[];
};

export type IntakeWorkflowEvent =
  | "intake_opened"
  | "file_selected"
  | "preview_complete"
  | "source_ingested"
  | "entities_admitted";

function asDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The browser could not read this file."));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  });
}

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
  const [file, setFile] = useState<File | null>(null);
  const [contentBase64, setContentBase64] = useState("");
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [library, setLibrary] = useState<DocumentLibraryRecord[]>([]);
  const [receipt, setReceipt] = useState<AdmissionReceipt["receipt"] | null>(null);
  const [candidateReceipt, setCandidateReceipt] = useState<NonNullable<AdmissionReceipt["candidate_admission"]> | null>(null);
  const [candidateAdmissionError, setCandidateAdmissionError] = useState("");
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set());
  const [admittedValues, setAdmittedValues] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [intakeOpen, setIntakeOpen] = useState(true);
  const [reviewPage, setReviewPage] = useState(0);
  const [candidateFilter, setCandidateFilter] = useState("");
  const [candidateSort, setCandidateSort] = useState<"source" | "type" | "value">("source");
  const [lastSelectedCandidate, setLastSelectedCandidate] = useState<string | null>(null);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState("");
  const [libraryDetail, setLibraryDetail] = useState<StoredDocumentDetail | null>(null);
  const [libraryDetailLoading, setLibraryDetailLoading] = useState(false);
  const [libraryDetailError, setLibraryDetailError] = useState("");
  const [storedSelection, setStoredSelection] = useState<Set<string>>(new Set());
  const [libraryFilter, setLibraryFilter] = useState("");
  const [librarySort, setLibrarySort] = useState<"newest" | "oldest" | "name" | "candidates">("newest");
  const [storedFilter, setStoredFilter] = useState("");
  const [storedSort, setStoredSort] = useState<"source" | "type" | "value">("source");
  const [storedPage, setStoredPage] = useState(0);
  const [storedAdmissionBusy, setStoredAdmissionBusy] = useState(false);
  const [storedAdmissionReceipt, setStoredAdmissionReceipt] = useState<string>("");
  const alive = useRef(true);
  const libraryRequests = useRef(createIntakeRequestScope());
  const candidateSource = preview?.entity_extraction.candidates ?? [];
  const filteredCandidates = candidateSource
    .filter((candidate) => {
      const query = candidateFilter.trim().toLocaleLowerCase();
      return !query || [candidate.raw_value, candidate.normalized_value, candidate.entity_type, candidate.rule_id]
        .some((value) => value.toLocaleLowerCase().includes(query));
    })
    .toSorted((left, right) => candidateSort === "type"
      ? left.entity_type.localeCompare(right.entity_type) || left.start_char - right.start_char
      : candidateSort === "value"
        ? left.normalized_value.localeCompare(right.normalized_value) || left.start_char - right.start_char
        : left.start_char - right.start_char);
  const page = candidatePage(filteredCandidates, reviewPage);
  const visibleCandidates = page.items;
  const visibleLibrary = library.filter((item) => [item.filename, item.source_kind, item.parser_state, item.detected_media_type]
    .some((value) => value.toLocaleLowerCase().includes(libraryFilter.trim().toLocaleLowerCase())))
    .toSorted((left, right) => librarySort === "name" ? left.filename.localeCompare(right.filename)
      : librarySort === "candidates" ? right.candidate_count - left.candidate_count
        : librarySort === "oldest" ? left.acquired_at.localeCompare(right.acquired_at)
          : right.acquired_at.localeCompare(left.acquired_at));
  const storedCandidates = (libraryDetail?.candidates ?? []).filter((candidate) =>
    [candidate.raw_value, candidate.normalized_value, candidate.entity_type]
      .some((value) => value.toLocaleLowerCase().includes(storedFilter.trim().toLocaleLowerCase())))
    .toSorted((left, right) => storedSort === "type" ? left.entity_type.localeCompare(right.entity_type) || left.start_char - right.start_char
      : storedSort === "value" ? left.normalized_value.localeCompare(right.normalized_value) || left.start_char - right.start_char
        : left.start_char - right.start_char);
  const storedCandidatePage = candidatePage(storedCandidates, storedPage);

  const toggleCandidateSelection = (candidate: (typeof candidateSource)[number], shiftKey: boolean) => {
    const checked = !selectedCandidates.has(candidate.selection_key);
    setSelectedCandidates((current) => {
      const next = new Set(current);
      const rangeStart = shiftKey && lastSelectedCandidate
        ? filteredCandidates.findIndex((item) => item.selection_key === lastSelectedCandidate)
        : -1;
      const rangeEnd = filteredCandidates.findIndex((item) => item.selection_key === candidate.selection_key);
      if (rangeStart >= 0 && rangeEnd >= 0) {
        const [start, end] = rangeStart < rangeEnd ? [rangeStart, rangeEnd] : [rangeEnd, rangeStart];
        for (const item of filteredCandidates.slice(start, end + 1)) next.add(item.selection_key);
      } else if (checked) next.add(candidate.selection_key);
      else next.delete(candidate.selection_key);
      return next;
    });
    setLastSelectedCandidate(candidate.selection_key);
  };

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

  const inspect = async () => {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setError("This preview accepts files up to 10 MiB.");
      return;
    }
    setBusy(true);
    setError("");
    setPreview(null);
    setContentBase64("");
    setReceipt(null);
    setCandidateReceipt(null);
    setCandidateAdmissionError("");
    setSelectedCandidates(new Set());
    setReviewPage(0);
    setAdmittedValues([]);
    try {
      const dataUrl = await asDataUrl(file);
      if (!alive.current) return;
      const marker = dataUrl.indexOf(",");
      if (marker < 0) throw new Error("The browser did not produce a valid file preview.");
      const encoded = dataUrl.slice(marker + 1);
      const response = await fetch("/api/documents/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          media_type: file.type || null,
          content_base64: encoded,
        }),
      });
      const result = await response.json() as DocumentPreview & { error?: string };
      if (!alive.current) return;
      if (!response.ok || result.error) throw new Error(result.error ?? "Document preview failed.");
      setContentBase64(encoded);
      setPreview(result);
      setSelectedCandidates(new Set());
      setReviewPage(0);
      onWorkflowEvent?.("preview_complete");
    } catch (reason) {
      if (alive.current) setError(reason instanceof Error ? reason.message : "Document preview failed.");
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const ingest = async () => {
    if (!file || !preview || !contentBase64) return;
    const selectedValues = [...new Set(preview.entity_extraction.candidates
      .filter((candidate) => selectedCandidates.has(candidate.selection_key))
      .map((candidate) => candidate.normalized_value))];
    setBusy(true);
    setError("");
    setReceipt(null);
    setCandidateReceipt(null);
    setCandidateAdmissionError("");
    try {
      const response = await fetch("/api/documents/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          media_type: file.type || null,
          content_base64: contentBase64,
          expected_sha256: preview.content_sha256,
          operator: "local analyst",
          expected_workspace: workspace,
          candidate_keys: [...selectedCandidates],
        }),
      });
      const result = await response.json() as AdmissionReceipt & { error?: string };
      if (!alive.current) return;
      if (!response.ok || result.error) throw new Error(result.error ?? "Document ingestion failed.");
      libraryRequests.current.invalidate();
      setLibraryLoading(false);
      setLibraryError("");
      setLibrary(result.library);
      setReceipt(result.receipt);
      setCandidateReceipt(result.candidate_admission ?? null);
      setAdmittedValues(result.candidate_admission ? selectedValues : []);
      setCandidateAdmissionError(result.candidate_admission_error ?? "");
      onWorkflowEvent?.(result.candidate_admission ? "entities_admitted" : "source_ingested");
      await onChanged?.();
    } catch (reason) {
      if (alive.current) setError(reason instanceof Error ? reason.message : "Document ingestion failed.");
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const retryCandidateAdmission = async () => {
    if (!receipt || selectedCandidates.size === 0) return;
    const selectedValues = [...new Set((preview?.entity_extraction.candidates ?? [])
      .filter((candidate) => selectedCandidates.has(candidate.selection_key))
      .map((candidate) => candidate.normalized_value))];
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/documents/candidates/admit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          occurrence_id: receipt.intake.occurrence_id,
          candidate_keys: [...selectedCandidates],
          operator: "local analyst",
          expected_workspace: workspace,
        }),
      });
      const result = await response.json() as {
        admitted?: boolean;
        receipt?: NonNullable<AdmissionReceipt["candidate_admission"]>;
        error?: string;
      };
      if (!alive.current) return;
      if (!response.ok || result.error || !result.receipt) {
        throw new Error(result.error ?? "Selected entity admission did not complete.");
      }
      setCandidateReceipt(result.receipt);
      setAdmittedValues(selectedValues);
      setCandidateAdmissionError("");
      onWorkflowEvent?.("entities_admitted");
      await onChanged?.();
    } catch (reason) {
      if (alive.current) setCandidateAdmissionError(
        reason instanceof Error ? reason.message : "Selected entity admission did not complete.",
      );
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const reviewStoredDocument = async (item: DocumentLibraryRecord) => {
    setLibraryDetailLoading(true);
    setLibraryDetailError("");
    setStoredAdmissionReceipt("");
    setLibraryDetail(null);
    setStoredSelection(new Set());
    try {
      const response = await fetch(`/api/documents/${encodeURIComponent(item.occurrence_id)}`, { cache: "no-store" });
      const result = await response.json() as StoredDocumentDetail & { error?: string };
      if (!response.ok || result.error) throw new Error(result.error ?? "Stored document details could not be loaded.");
      if (alive.current) setLibraryDetail(result);
    } catch (reason) {
      if (alive.current) setLibraryDetailError(reason instanceof Error ? reason.message : "Stored document details could not be loaded.");
    } finally {
      if (alive.current) setLibraryDetailLoading(false);
    }
  };

  const admitStoredCandidates = async () => {
    if (!libraryDetail || storedSelection.size === 0) return;
    setStoredAdmissionBusy(true);
    setLibraryDetailError("");
    try {
      const response = await fetch("/api/documents/candidates/admit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          occurrence_id: libraryDetail.occurrence_id,
          candidate_keys: [...storedSelection],
          operator: "local analyst",
          expected_workspace: workspace,
        }),
      });
      const result = await response.json() as { receipt?: NonNullable<AdmissionReceipt["candidate_admission"]>; error?: string };
      if (!response.ok || result.error || !result.receipt) throw new Error(result.error ?? "Selected candidates could not be admitted.");
      setStoredSelection(new Set());
      setStoredAdmissionReceipt(`${result.receipt.admitted_candidate_count} candidate${result.receipt.admitted_candidate_count === 1 ? "" : "s"} admitted; ${result.receipt.new_entity_count} new workspace entit${result.receipt.new_entity_count === 1 ? "y" : "ies"}.`);
      await loadLibrary();
      await onChanged?.();
    } catch (reason) {
      if (alive.current) setLibraryDetailError(reason instanceof Error ? reason.message : "Selected candidates could not be admitted.");
    } finally {
      if (alive.current) setStoredAdmissionBusy(false);
    }
  };

  return (
    <details className="document-intake" open={intakeOpen} onToggle={(event) => {
      setIntakeOpen(event.currentTarget.open);
      if (event.currentTarget.open) onWorkflowEvent?.("intake_opened");
    }}>
      <summary>ADD INDICATORS &amp; REPORTS · {libraryLoading ? "LOADING LIBRARY" : libraryError ? "LIBRARY UNAVAILABLE" : `${library.length} SOURCES STORED`}</summary>
      <p><b>Destination workspace: {workspace}</b>. Switching workspaces clears this unfinished preview and selection.</p>
      <p>
        Start here with a text list or report. 1. Choose a file. 2. Preview it locally.
        3. Select the candidate entities you recognize. 4. Ingest the source and add only
        those selected entities to this workspace. Preview alone changes nothing.
      </p>
      <div className="document-intake-controls">
        <input
          type="file"
          disabled={busy}
          accept=".txt,.md,.html,.htm,.csv,.json,.jsonl,.ndjson,.eml,.pdf,text/*,application/json,application/pdf,message/rfc822"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setPreview(null);
            setContentBase64("");
            setReceipt(null);
            setCandidateReceipt(null);
            setCandidateAdmissionError("");
            setSelectedCandidates(new Set());
            setCandidateFilter("");
            setCandidateSort("source");
            setLastSelectedCandidate(null);
            setAdmittedValues([]);
            setReviewPage(0);
            setError("");
            if (event.target.files?.[0]) onWorkflowEvent?.("file_selected");
          }}
          aria-label="Choose a document to preview locally"
        />
        <button type="button" data-action="preview-document" disabled={!file || busy} onClick={() => void inspect()}>
          {busy ? "INSPECTING…" : "PREVIEW LOCALLY"}
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {preview && (
        <section className={`document-preview state-${preview.state}`} aria-live="polite">
          <header>
            <b>{preview.filename}</b>
            <span>{preview.state.toUpperCase()} · {preview.detected_media_type} · {preview.size_bytes} bytes</span>
          </header>
          <p className="truth-note">{preview.truth_boundary}</p>
          {preview.warnings.map((item) => <p key={item}><b>WARNING</b> {item}</p>)}
          {preview.errors.map((item) => <p className="error" key={item}><b>ERROR</b> {item}</p>)}
          {preview.skipped.map((item) => <p key={item}><b>NOT PARSED</b> {item}</p>)}
          <pre>{preview.output_text || "No preview text was produced."}</pre>
          <details className="document-candidates" open>
            <summary>
              ENTITY CANDIDATES · {preview.entity_extraction.candidate_count}
            </summary>
            <p className="truth-note">{preview.entity_extraction.truth_boundary} Use the filter and sort controls to narrow the list; click checkboxes, Shift-click for a range, or select all visible matches before admission.</p>
            {preview.entity_extraction.warnings.map((item) => (
              <p key={item}><b>LIMIT</b> {item}</p>
            ))}
            {preview.entity_extraction.candidates.length > 0 ? (
              <>
              <div className="candidate-selection-controls">
                <label className="intake-search"><span>Find candidates</span>
                <input value={candidateFilter} onChange={(event) => { setCandidateFilter(event.target.value); setReviewPage(0); }} placeholder="Filter value, type, or rule" aria-label="Filter entity candidates" disabled={busy || Boolean(receipt)} /></label>
                <label><span>Order</span><select value={candidateSort} onChange={(event) => { setCandidateSort(event.target.value as typeof candidateSort); setReviewPage(0); }} aria-label="Sort entity candidates" disabled={busy || Boolean(receipt)}>
                  <option value="source">Source order</option><option value="type">Entity type</option><option value="value">Value A–Z</option>
                </select></label>
              </div><div className="candidate-selection-controls selection-actions"><b>{selectedCandidates.size} selected</b>
                <button type="button" disabled={busy || Boolean(receipt) || visibleCandidates.length === 0} onClick={() => setSelectedCandidates((current) => selectCandidatePage(current, visibleCandidates.map((item) => item.selection_key)))}>SELECT PAGE ({visibleCandidates.length})</button>
                <button type="button" disabled={busy || Boolean(receipt) || filteredCandidates.length === 0} onClick={() => setSelectedCandidates((current) => selectCandidatePage(current, filteredCandidates.map((item) => item.selection_key)))}>SELECT ALL MATCHES ({filteredCandidates.length})</button>
                <button type="button" disabled={busy || Boolean(receipt) || selectedCandidates.size === 0} onClick={() => setSelectedCandidates(new Set())}>CLEAR SELECTION</button>
              </div>
              <nav className="candidate-selection-controls" aria-label="Candidate review pages">
                <button type="button" disabled={busy || page.page === 0} onClick={() => setReviewPage(page.page - 1)}>PREVIOUS</button>
                <span role="status">Page {page.page + 1} of {page.pageCount} · {page.start + 1}–{page.start + visibleCandidates.length} of {preview.entity_extraction.candidates.length} reviewable candidates</span>
                <button type="button" disabled={busy || page.page + 1 >= page.pageCount} onClick={() => setReviewPage(page.page + 1)}>NEXT</button>
              </nav>
              <ol className="selectable-candidates">
                {visibleCandidates.map((candidate) => (
                  <li key={candidate.id} className={selectedCandidates.has(candidate.selection_key) ? "selected" : ""}>
                    <label>
                    <input
                      type="checkbox"
                      disabled={busy || Boolean(receipt)}
                      checked={selectedCandidates.has(candidate.selection_key)}
                      onChange={(event) => toggleCandidateSelection(candidate, Boolean((event.nativeEvent as MouseEvent | undefined)?.shiftKey))}
                      aria-label={`Add ${candidate.normalized_value} to the workspace when the source is ingested`}
                    />
                    <div>
                      <b>{candidate.raw_value}</b>
                      <span>{candidate.entity_type}</span>
                    </div>
                    <code>{candidate.normalized_value}</code>
                    <small>
                      line {candidate.start_line}, column {candidate.start_column} · characters {candidate.start_char}–{candidate.end_char} · UTF-8 bytes {candidate.start_byte}–{candidate.end_byte} · {candidate.rule_id}@{candidate.rule_version}
                    </small>
                    {candidate.normalization_note && <small>{candidate.normalization_note}</small>}
                    </label>
                  </li>
                ))}
              </ol>
              </>
            ) : (
              <p>No qualified entity candidates were found in the bounded parser output.</p>
            )}
            {preview.entity_extraction.candidate_count > visibleCandidates.length && (
              <small>
                Selections are kept when you change pages. Select this page adds only the
                displayed candidates; it never selects unseen pages. Extraction limits and
                skipped content are reported separately in the parser warnings above.
              </small>
            )}
          </details>
          <small>Preview is temporary until you explicitly choose a source-admission action below.</small>
          <div className="document-admission">
            <p>
              Ingestion stores the exact source bytes, parser receipt, and every reviewable
              candidate. {selectedCandidates.size > 0
                ? `${selectedCandidates.size} selected candidate${selectedCandidates.size === 1 ? "" : "s"} will also become workspace entities with source provenance.`
                : "No candidates are selected, so this will store the source only."}{" "}
              It does not declare a candidate malicious or make the source claim true.
            </p>
            <button type="button" disabled={busy || preview.state === "failed" || Boolean(receipt)} onClick={() => void ingest()}>
              {busy
                ? "INGESTING…"
                : receipt
                  ? "✓ INGESTED"
                  : selectedCandidates.size
                    ? `INGEST SOURCE + ADD ${selectedCandidates.size} ${selectedCandidates.size === 1 ? "ENTITY" : "ENTITIES"}`
                    : "INGEST SOURCE ONLY"}
            </button>
          </div>
        </section>
      )}
      {receipt && (
        <p className="document-receipt" role="status">
          <b>INGESTION RECEIPT</b> {receipt.candidate_count} candidates stored with source
          provenance. {receipt.truth_boundary}
        </p>
      )}
      {candidateReceipt && (
        <p className="candidate-admission-receipt" role="status">
          <b>ENTITY ADMISSION RECEIPT</b> {candidateReceipt.admitted_candidate_count} selected
          candidate{candidateReceipt.admitted_candidate_count === 1 ? "" : "s"} admitted as {candidateReceipt.entity_count}{" "}
          workspace entit{candidateReceipt.entity_count === 1 ? "y" : "ies"}; {candidateReceipt.new_entity_count} new.
          {" "}{candidateReceipt.truth_boundary}
        </p>
      )}
      {candidateAdmissionError && receipt && (
        <section className="candidate-admission-warning" role="alert">
          <div>
            <b>SOURCE STORED · ENTITY ADMISSION INCOMPLETE</b>
            <p>{candidateAdmissionError}</p>
            <small>
              Retrying uses the stored source occurrence and the same reviewed selection keys.
              It does not store a second copy of the source or duplicate already admitted entities.
            </small>
          </div>
          <button type="button" disabled={busy || selectedCandidates.size === 0} onClick={() => void retryCandidateAdmission()}>
            {busy ? "RETRYING…" : "RETRY ENTITY ADMISSION"}
          </button>
        </section>
      )}
      {candidateReceipt && admittedValues.length > 0 && onUseIndicator && (
        <section className="admitted-indicator-actions" aria-label="Choose an added indicator to investigate">
          <h3>Choose an added indicator to investigate</h3>
          <p>These selected indicators are stored. Use one to prepare the command, then choose Investigate to run enrichment. Adding a source does not run enrichment.</p>
          <div className="candidate-selection-controls">
            {admittedValues.map((value) => <button type="button" key={value} data-action="use-admitted-indicator" onClick={() => onUseIndicator(value)}>Use {value}</button>)}
          </div>
        </section>
      )}
      <section className="document-library" aria-label="Stored document library">
        <header><b>DOCUMENT LIBRARY</b><span>{library.length} source occurrence{library.length === 1 ? "" : "s"}</span></header>
        {libraryLoading && <p role="status">Loading the document library for {workspace}…</p>}
        {libraryError && <div role="alert"><p>{libraryError}</p>{library.length > 0 && <small>Showing the last successfully loaded records; this list may be out of date.</small>}<button type="button" disabled={libraryLoading} onClick={() => void loadLibrary()}>RETRY LIBRARY</button></div>}
      {library.length ? (<>
          <div className="candidate-selection-controls">
            <label className="intake-search"><span>Find sources</span><input value={libraryFilter} onChange={(event) => setLibraryFilter(event.target.value)} placeholder="Filter stored sources" aria-label="Filter stored sources" /></label>
            <label><span>Order</span><select value={librarySort} onChange={(event) => setLibrarySort(event.target.value as typeof librarySort)} aria-label="Sort stored sources">
              <option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="name">Filename</option><option value="candidates">Most candidates</option>
            </select></label>
            <span role="status">{visibleLibrary.length} of {library.length} sources</span>
          </div>
          <ol>
            {visibleLibrary.map((item) => (
              <li key={item.occurrence_id}>
                <div><b title={item.filename}>{item.filename}</b><span>{item.parser_state} · {item.detected_media_type}</span></div>
                <small>{item.candidate_count} candidates · {item.size_bytes} bytes · ingested {new Date(item.acquired_at).toLocaleString()}</small>
                <code title={`Full SHA-256: ${item.content_sha256}`}>SHA-256 <span className="document-hash">{item.content_sha256}</span></code>
                <button type="button" disabled={libraryDetailLoading} onClick={() => void reviewStoredDocument(item)}>
                  {libraryDetail?.occurrence_id === item.occurrence_id ? "✓ REVIEWING" : "REVIEW STORED SOURCE"}
                </button>
              </li>
            ))}
          </ol>
          </>
        ) : !libraryLoading && !libraryError ? <p>No documents have been ingested into this workspace.</p> : null}
        <small>Library entries are persistent workspace records. Candidate strings remain separate until explicitly selected for entity admission. Raw source bytes never enter the DOM after ingestion.</small>
        {libraryDetailLoading && <p role="status">Loading the stored parser receipt and candidate list…</p>}
        {libraryDetailError && <p className="error" role="alert">{libraryDetailError}</p>}
        {libraryDetail && (
          <section className="document-library-detail" aria-label={`Stored source details for ${libraryDetail.filename}`}>
            <header><b>STORED SOURCE REVIEW</b><button type="button" onClick={() => { setLibraryDetail(null); setStoredSelection(new Set()); }}>CLOSE REVIEW</button></header>
            <p><b>{libraryDetail.filename}</b> · {libraryDetail.parser.state} · {libraryDetail.size_bytes} bytes</p>
            <p><code title={`Full SHA-256: ${libraryDetail.content_sha256}`}>SHA-256 <span className="document-hash">{libraryDetail.content_sha256}</span></code></p>
            <p className="truth-note">{libraryDetail.truth_boundary}</p>
            {storedAdmissionReceipt && <p className="candidate-admission-receipt" role="status"><b>ENTITY ADMISSION RECEIPT</b> {storedAdmissionReceipt}</p>}
            {libraryDetail.parser.warnings.map((item) => <p key={item}><b>WARNING</b> {item}</p>)}
            {libraryDetail.parser.errors.map((item) => <p className="error" key={item}><b>ERROR</b> {item}</p>)}
            <details>
              <summary>STORED PARSER OUTPUT</summary>
              <pre>{libraryDetail.parser.output_text || "No parser output was stored."}</pre>
            </details>
            <details open>
              <summary>STORED ENTITY CANDIDATES · {libraryDetail.candidates.length}</summary>
              {libraryDetail.candidates.length ? <>
                <div className="candidate-selection-controls">
                <label className="intake-search"><span>Find candidates</span>
                <input value={storedFilter} onChange={(event) => { setStoredFilter(event.target.value); setStoredPage(0); }} placeholder="Filter stored candidates" aria-label="Filter stored candidates" /></label>
                <label><span>Order</span><select value={storedSort} onChange={(event) => { setStoredSort(event.target.value as typeof storedSort); setStoredPage(0); }} aria-label="Sort stored candidates">
                  <option value="source">Source order</option><option value="type">Entity type</option><option value="value">Value A–Z</option>
                </select></label>
                </div><div className="candidate-selection-controls selection-actions"><b>{storedSelection.size} selected</b>
                <button type="button" disabled={storedAdmissionBusy || storedCandidatePage.items.length === 0} onClick={() => setStoredSelection((current) => selectCandidatePage(current, storedCandidatePage.items.map((item) => item.selection_key)))}>SELECT PAGE ({storedCandidatePage.items.length})</button>
                <button type="button" disabled={storedAdmissionBusy || storedCandidates.length === 0} onClick={() => setStoredSelection((current) => selectCandidatePage(current, storedCandidates.map((item) => item.selection_key)))}>SELECT ALL MATCHES ({storedCandidates.length})</button>
                <button type="button" disabled={storedAdmissionBusy || storedSelection.size === 0} onClick={() => void admitStoredCandidates()}>
                  {storedAdmissionBusy ? "ADMITTING…" : "ADMIT SELECTED CANDIDATES"}
                </button>
                <button type="button" disabled={storedAdmissionBusy || storedSelection.size === 0} onClick={() => setStoredSelection(new Set())}>CLEAR SELECTION</button>
                </div>
                <nav className="candidate-selection-controls" aria-label="Stored candidate pages">
                  <button type="button" disabled={storedPage <= 0} onClick={() => setStoredPage(storedCandidatePage.page - 1)}>PREVIOUS</button>
                  <span role="status">Page {storedCandidatePage.page + 1} of {storedCandidatePage.pageCount} · {storedCandidates.length} matches</span>
                  <button type="button" disabled={storedCandidatePage.page + 1 >= storedCandidatePage.pageCount} onClick={() => setStoredPage(storedCandidatePage.page + 1)}>NEXT</button>
                </nav>
                <ol className="selectable-candidates">
                  {storedCandidatePage.items.map((candidate) => <li key={candidate.id} className={storedSelection.has(candidate.selection_key) ? "selected" : ""}>
                    <label><input type="checkbox" disabled={storedAdmissionBusy} checked={storedSelection.has(candidate.selection_key)} onChange={(event) => setStoredSelection((current) => {
                      const next = new Set(current);
                      if (event.target.checked) next.add(candidate.selection_key); else next.delete(candidate.selection_key);
                      return next;
                    })} aria-label={`Admit ${candidate.normalized_value} from the stored source`} />
                    <div><b>{candidate.raw_value}</b><span>{candidate.entity_type}</span></div><code>{candidate.normalized_value}</code>
                    <small>line {candidate.start_line}, column {candidate.start_column} · characters {candidate.start_char}–{candidate.end_char}</small>
                    {candidate.normalization_note && <small>{candidate.normalization_note}</small>}
                  </label></li>)}
                </ol>
              </> : <p>No entity candidates were stored for this source.</p>}
            </details>
          </section>
        )}
      </section>
    </details>
  );
}
