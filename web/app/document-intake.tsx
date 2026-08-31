"use client";

import { useState } from "react";

type DocumentPreview = {
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

function asDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The browser could not read this file."));
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.readAsDataURL(file);
  });
}

export function DocumentIntake() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

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
      const response = await fetch("/api/documents/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          media_type: file.type || null,
          content_base64: dataUrl.slice(marker + 1),
        }),
      });
      const result = await response.json() as DocumentPreview & { error?: string };
      if (!response.ok || result.error) throw new Error(result.error ?? "Document preview failed.");
      setPreview(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Document preview failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="document-intake">
      <summary>PREVIEW A DOCUMENT</summary>
      <p>
        Inspect selected bytes locally before ingestion. Preview creates no evidence, entities,
        relationships, or model request.
      </p>
      <div className="document-intake-controls">
        <input
          type="file"
          accept=".txt,.md,.html,.htm,.csv,.json,.jsonl,.ndjson,.eml,.pdf,text/*,application/json,application/pdf,message/rfc822"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setPreview(null);
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
          <small>Preview is temporary. Admission and storage controls arrive in the governed ingestion workflow.</small>
        </section>
      )}
    </details>
  );
}
