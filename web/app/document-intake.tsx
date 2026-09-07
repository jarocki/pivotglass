"use client";

import { useEffect, useState } from "react";

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

type AdmissionReceipt = {
  admitted: boolean;
  receipt: {
    candidate_count: number;
    truth_boundary: string;
    intake: { occurrence_id: string; reused_content: boolean };
  };
  library: DocumentLibraryRecord[];
};

function asDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The browser could not read this file."));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  });
}

export function DocumentIntake({ onChanged }: { onChanged?: () => Promise<void> | void }) {
  const [file, setFile] = useState<File | null>(null);
  const [contentBase64, setContentBase64] = useState("");
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [library, setLibrary] = useState<DocumentLibraryRecord[]>([]);
  const [receipt, setReceipt] = useState<AdmissionReceipt["receipt"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadLibrary = async () => {
    const response = await fetch("/api/documents", { cache: "no-store" });
    const result = await response.json() as { documents?: DocumentLibraryRecord[]; error?: string };
    if (!response.ok || result.error) throw new Error(result.error ?? "Document library failed.");
    setLibrary(result.documents ?? []);
  };

  useEffect(() => { void loadLibrary().catch(() => undefined); }, []);

  const inspect = async () => {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setError("This preview accepts files up to 10 MiB.");
      return;
    }
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      const dataUrl = await asDataUrl(file);
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
      if (!response.ok || result.error) throw new Error(result.error ?? "Document preview failed.");
      setContentBase64(encoded);
      setPreview(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Document preview failed.");
    } finally {
      setBusy(false);
    }
  };

  const ingest = async () => {
    if (!file || !preview || !contentBase64) return;
    setBusy(true);
    setError("");
    setReceipt(null);
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
        }),
      });
      const result = await response.json() as AdmissionReceipt & { error?: string };
      if (!response.ok || result.error) throw new Error(result.error ?? "Document ingestion failed.");
      setLibrary(result.library);
      setReceipt(result.receipt);
      await onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Document ingestion failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="document-intake">
      <summary>DOCUMENT INTAKE &amp; LIBRARY · {library.length} STORED</summary>
      <p>
        1. Choose a file. 2. Preview and review extracted candidates locally. 3. Select
        <b> INGEST INTO WORKSPACE</b> to store the source, parser receipt, and candidate provenance.
        Preview alone changes nothing.
      </p>
      <div className="document-intake-controls">
        <input
          type="file"
          accept=".txt,.md,.html,.htm,.csv,.json,.jsonl,.ndjson,.eml,.pdf,text/*,application/json,application/pdf,message/rfc822"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setPreview(null);
            setContentBase64("");
            setReceipt(null);
            setError("");
          }}
          aria-label="Choose a document to preview locally"
        />
        <button type="button" disabled={!file || busy} onClick={() => void inspect()}>
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
          <details className="document-candidates">
            <summary>
              ENTITY CANDIDATES · {preview.entity_extraction.candidate_count}
            </summary>
            <p className="truth-note">{preview.entity_extraction.truth_boundary}</p>
            {preview.entity_extraction.warnings.map((item) => (
              <p key={item}><b>LIMIT</b> {item}</p>
            ))}
            {preview.entity_extraction.candidates.length > 0 ? (
              <ol>
                {preview.entity_extraction.candidates.slice(0, 100).map((candidate) => (
                  <li key={candidate.id}>
                    <div>
                      <b>{candidate.raw_value}</b>
                      <span>{candidate.entity_type}</span>
                    </div>
                    <code>{candidate.normalized_value}</code>
                    <small>
                      line {candidate.start_line}, column {candidate.start_column} · characters {candidate.start_char}–{candidate.end_char} · UTF-8 bytes {candidate.start_byte}–{candidate.end_byte} · {candidate.rule_id}@{candidate.rule_version}
                    </small>
                    {candidate.normalization_note && <small>{candidate.normalization_note}</small>}
                  </li>
                ))}
              </ol>
            ) : (
              <p>No qualified entity candidates were found in the bounded parser output.</p>
            )}
            {preview.entity_extraction.candidate_count > 100 && (
              <small>Showing the first 100 candidates. The local preview receipt counted {preview.entity_extraction.candidate_count}.</small>
            )}
          </details>
          <small>Preview is temporary until you explicitly choose INGEST INTO WORKSPACE.</small>
          <div className="document-admission">
            <p>
              Ingestion stores the exact source bytes by SHA-256, this parser receipt, and the
              candidates above. It does not declare those candidates malicious or true.
            </p>
            <button type="button" disabled={busy || preview.state === "failed" || Boolean(receipt)} onClick={() => void ingest()}>
              {busy ? "INGESTING…" : receipt ? "✓ INGESTED" : "INGEST INTO WORKSPACE"}
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
      <section className="document-library" aria-label="Stored document library">
        <header><b>DOCUMENT LIBRARY</b><span>{library.length} source occurrence{library.length === 1 ? "" : "s"}</span></header>
        {library.length ? (
          <ol>
            {library.map((item) => (
              <li key={item.occurrence_id}>
                <div><b title={item.filename}>{item.filename}</b><span>{item.parser_state} · {item.detected_media_type}</span></div>
                <small>{item.candidate_count} candidates · {item.size_bytes} bytes · ingested {new Date(item.acquired_at).toLocaleString()}</small>
                <code title={item.content_sha256}>SHA-256 {item.content_sha256.slice(0, 12)}…</code>
              </li>
            ))}
          </ol>
        ) : <p>No documents have been ingested into this workspace.</p>}
        <small>Library entries are persistent workspace records. Raw source bytes never enter the DOM after ingestion.</small>
      </section>
    </details>
  );
}
