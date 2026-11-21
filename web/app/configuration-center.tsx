"use client";

import { useEffect, useMemo, useState } from "react";

type CredentialSource = "config" | "environment" | "missing" | "mixed" | "not-required";
type ModelState = {
  enabled: boolean;
  provider: string;
  provider_name: string;
  model: string;
  model_id: string;
  source: string;
  credential_source: CredentialSource;
  advisor_enabled: boolean;
};
type ProviderState = {
  id: string;
  display_name: string;
  selected: boolean;
  needs_api_key: boolean;
  credential_source: CredentialSource;
  endpoint: string;
  default_base_url: string;
  base_url_override?: string | null;
  requires_base_url?: boolean;
  note?: string;
};
type ServiceState = {
  id: string;
  display_name: string;
  enabled: boolean;
  credential_source: CredentialSource;
  credential_fields: Array<{ key: string; label: string; credential_source: CredentialSource; required: boolean }>;
  docs_url: string;
  test_endpoint: string;
  default_base_url: string;
  base_url_override?: string | null;
};
type ConfigurationState = {
  model: ModelState;
  providers: ProviderState[];
  services: ServiceState[];
};
type ModelProfile = {
  model_id: string;
  runtime_model: string;
  strengths: string[];
  limitations: string[];
  context_tokens?: number | null;
  supports_tools?: boolean | null;
  supports_vision?: boolean | null;
  supports_reasoning?: boolean | null;
};
type Health = {
  state: string;
  summary: string;
  checked_endpoint?: string | null;
  available_models?: number | null;
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error ?? `Request failed (${response.status})`);
  return payload as T;
}

/**
 * API base URL for one provider or service. The registry default is shown as the
 * placeholder; saving stores only an override (gateway or proxy), and Reset clears it.
 */
function BaseUrlField({ id, label, defaultUrl, override, required, busy, onSave }: {
  id: string;
  label: string;
  defaultUrl: string;
  override?: string | null;
  required?: boolean;
  busy: boolean;
  onSave: (value: string | null) => Promise<boolean>;
}) {
  // The field shows the effective URL as real text: the override, else the default.
  const effective = override ?? defaultUrl;
  const [draft, setDraft] = useState(effective);
  useEffect(() => { setDraft(effective); }, [effective]);
  const normalized = draft.trim().replace(/\/+$/, "");
  const changed = normalized !== effective;
  // Saving the default (or nothing) clears the override instead of storing a copy.
  const save = () => onSave(!normalized || normalized === defaultUrl ? null : normalized);
  const hostOf = (value: string) => { try { return new URL(value).host; } catch { return ""; } };
  const newHost = changed ? hostOf(normalized) : "";
  const redirected = Boolean(newHost) && newHost !== hostOf(defaultUrl);
  return <div className="base-url-field">
    <label htmlFor={`base-url-${id}`}>{label}{!override && defaultUrl && <span className="credential-presence">Default</span>}{override && <span className="credential-presence">Gateway override</span>}</label>
    <div>
      <input
        id={`base-url-${id}`}
        type="url"
        inputMode="url"
        spellCheck={false}
        value={draft}
        placeholder={required ? "Required: https://…" : "https://…"}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter" && changed) void save(); }}
      />
      {changed && <button disabled={busy} onClick={() => void save()}>Save</button>}
      {override && !changed && <button disabled={busy} onClick={() => void onSave(null)}>{defaultUrl ? "Use default" : "Clear"}</button>}
    </div>
    {redirected && <small className="base-url-warning" role="note">Requests — and any saved key for this service — will go to <b>{newHost}</b>. Save only a gateway you control or trust.</small>}
  </div>;
}

export function ConfigurationCenter({ onClose }: { onClose: () => void }) {
  const [configuration, setConfiguration] = useState<ConfigurationState | null>(null);
  const [providerId, setProviderId] = useState("");
  const [providerSecret, setProviderSecret] = useState("");
  const [serviceSecrets, setServiceSecrets] = useState<Record<string, string[]>>({});
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [notice, setNotice] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [serviceOutcome, setServiceOutcome] = useState<Record<string, { saved: boolean | null; health: Health }>>({});
  const [busy, setBusy] = useState("");

  const provider = useMemo(
    () => configuration?.providers.find((item) => item.id === providerId),
    [configuration, providerId],
  );

  async function refresh() {
    const next = await requestJson<ConfigurationState>("/api/configuration");
    setConfiguration(next);
    setProviderId((current) => current || next.model.provider);
  }

  useEffect(() => {
    refresh().catch((reason) => setNotice(String(reason)));
  }, []);

  async function update(body: Record<string, unknown>) {
    setBusy(String(body.action ?? "update"));
    setHealth(null);
    try {
      const result = await requestJson<{
        saved: boolean;
        health?: Health;
        configuration?: ConfigurationState;
      }>("/api/configuration/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (result.health) {
        if (body.action === "service-credentials") setServiceOutcome((current) => ({ ...current, [String(body.id)]: { saved: result.saved, health: result.health! } }));
        else setHealth(result.health);
      }
      if (result.configuration) setConfiguration(result.configuration);
      else await refresh();
      setNotice(result.saved
        ? body.action === "service-credentials"
          ? result.health?.state === "ready"
            ? "Credential saved and service access verified. Enable the service to use it."
            : "Credential saved. Service access is not verified; review the test result. Enable the service to use it."
          : "Configuration saved."
        : "Nothing was saved; correct the test failure first.");
      return result.saved;
    } catch (reason) {
      setNotice(String(reason));
      return false;
    } finally {
      setBusy("");
    }
  }

  async function check(kind: "provider" | "service", id: string, values?: string[]) {
    setBusy(`check-${id}`);
    setHealth(null);
    try {
      const result = await requestJson<Health>("/api/configuration/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          id,
          ...(kind === "provider" && providerSecret ? { secret: providerSecret } : {}),
          ...(values?.some(Boolean) ? { values } : {}),
        }),
      });
      if (kind === "service") setServiceOutcome((current) => ({ ...current, [id]: { saved: null, health: result } }));
      else setHealth(result);
    } catch (reason) {
      setNotice(String(reason));
    } finally {
      setBusy("");
    }
  }

  async function loadModels() {
    setBusy("models");
    setModels([]);
    try {
      const result = await requestJson<{ models: ModelProfile[]; notice: string }>(
        `/api/models?provider=${encodeURIComponent(providerId)}`,
      );
      setModels(result.models);
      setNotice(result.notice);
    } catch (reason) {
      setNotice(String(reason));
    } finally {
      setBusy("");
    }
  }

  if (!configuration) {
    return <section className="configuration-center loading" role="dialog" aria-modal="true" aria-label="Configuration"><button className="close" onClick={onClose} aria-label="Close configuration">×</button><p>Reading masked configuration…</p></section>;
  }

  return <section className="configuration-center" role="dialog" aria-modal="true" aria-labelledby="configuration-heading">
    <button className="close" onClick={onClose} aria-label="Close configuration">×</button>
    <span className="eyebrow">Local control · secrets stay out of logs and model prompts</span>
    <h2 id="configuration-heading" tabIndex={-1}>Configuration</h2>

    <div className="configuration-grid">
      <article className="configuration-section">
        <header><div><h3>AI model</h3><p>{configuration.model.provider_name} · {configuration.model.model}</p></div><span className={`health-state ${configuration.model.enabled ? "ready" : "disabled"}`}>{configuration.model.enabled ? "Enabled" : "Disabled"}</span></header>
        <div className="configuration-actions">
          <button onClick={() => update({ action: "model-enabled", enabled: !configuration.model.enabled })}>{configuration.model.enabled ? "Disable synthesis" : "Enable synthesis"}</button>
          <button onClick={() => update({ action: "advisor-enabled", enabled: !configuration.model.advisor_enabled })}>{configuration.model.advisor_enabled ? "Disable advisor" : "Enable advisor"}</button>
        </div>
        <dl className="configuration-facts">
          <div><dt>Selection source</dt><dd>{configuration.model.source}</dd></div>
          <div><dt>Credential</dt><dd>{configuration.model.credential_source}</dd></div>
          <div><dt>Advisor</dt><dd>{configuration.model.advisor_enabled ? "periodic local suggestions" : "off"}</dd></div>
        </dl>
      </article>

      <article className="configuration-section provider-section">
        <header><div><h3>Model provider</h3><p>Live checks happen only when you request them.</p></div></header>
        <label>Platform<select value={providerId} onChange={(event) => { setProviderId(event.target.value); setModels([]); setHealth(null); }}>{configuration.providers.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
        {provider && provider.id !== "ollama" && <label>{provider.needs_api_key ? "New credential" : "Gateway key (optional)"}<input type="password" autoComplete="new-password" value={providerSecret} onChange={(event) => setProviderSecret(event.target.value)} placeholder={provider.needs_api_key && provider.credential_source === "missing" ? "Required" : "Leave blank to keep current"} /></label>}
        <p className="credential-note">Credential source: <b>{provider?.credential_source}</b>{provider?.credential_source === "environment" && " · environment-owned values are read-only"}</p>
        <div className="configuration-actions">
          <button disabled={Boolean(busy)} onClick={() => check("provider", providerId)}>{busy === `check-${providerId}` ? "CHECKING…" : "Check access"}</button>
          {provider && provider.id !== "ollama" && <button disabled={!providerSecret || Boolean(busy)} onClick={async () => { if (await update({ action: "provider-credential", id: providerId, secret: providerSecret, verify: true })) setProviderSecret(""); }}>Save + test</button>}
          <button disabled={Boolean(busy)} onClick={loadModels}>{busy === "models" ? "LOADING…" : "View available models"}</button>
          {provider?.credential_source === "config" && <button className="danger-subtle" disabled={Boolean(busy)} onClick={() => update({ action: "remove-provider-credential", id: providerId })}>Remove stored key</button>}
        </div>
        {provider && <BaseUrlField
          id={provider.id}
          label="API base URL"
          defaultUrl={provider.default_base_url}
          override={provider.base_url_override}
          required={provider.requires_base_url}
          busy={Boolean(busy)}
          onSave={(value) => update({ action: "endpoint-override", id: provider.id, base_url: value })}
        />}
        {provider?.note && <p className="credential-note">{provider.note}</p>}
        <small>Models list: {provider?.endpoint}</small>
      </article>
    </div>

    {health && <div className={`configuration-health ${health.state}`} role="status"><b>{health.state.toUpperCase()}</b><span>{health.summary}</span>{health.checked_endpoint && <small>{health.checked_endpoint}</small>}</div>}
    {notice && <p className="configuration-notice" role="status">{notice}</p>}

    {models.length > 0 && <section className="model-catalog" aria-label="Available models">
      <header><h3>Available models</h3><span>{models.length} returned by {provider?.display_name}</span></header>
      <div className="model-cards">{models.map((model) => <article key={model.model_id} className={model.runtime_model === configuration.model.model ? "selected" : ""}>
        <header><b>{model.model_id}</b>{model.runtime_model === configuration.model.model && <span>Selected</span>}</header>
        <p><strong>Strengths</strong> {model.strengths.join(" ")}</p>
        <p><strong>Limitations</strong> {model.limitations.join(" ")}</p>
        <div className="model-tags">{model.supports_tools && <span>Tools</span>}{model.supports_vision && <span>Vision</span>}{model.supports_reasoning && <span>Reasoning</span>}{model.context_tokens && <span>{model.context_tokens.toLocaleString()} CONTEXT</span>}</div>
        <button disabled={Boolean(busy) || model.runtime_model === configuration.model.model} onClick={() => update({ action: "select-model", id: providerId, model_id: model.model_id })}>Select</button>
      </article>)}</div>
    </section>}

    <section className="service-catalog" aria-label="Intelligence APIs">
      <header><h3>Intelligence APIs</h3><span>Save a credential, test access, and enable each service separately</span></header>
      <div>{configuration.services.map((service) => {
        const values = serviceSecrets[service.id] ?? service.credential_fields.map(() => "");
        return <article key={service.id}>
          <header><div><b>{service.display_name}</b></div><button onClick={() => update({ action: "service-enabled", id: service.id, enabled: !service.enabled })}>{service.enabled ? "Enabled" : "Disabled"}</button></header>
          <BaseUrlField
            id={service.id}
            label="API base URL"
            defaultUrl={service.default_base_url}
            override={service.base_url_override}
            busy={Boolean(busy)}
            onSave={(value) => update({ action: "endpoint-override", id: service.id, base_url: value })}
          />
          <small className="service-test-endpoint">Test: {service.test_endpoint}</small>
          <div className="service-credential-fields">{service.credential_fields.map((field, index) => <label key={field.key}>{field.label}<span className="credential-presence">{field.credential_source === "config" ? "SAVED IN PIVOTGLASS · ••••••••" : field.credential_source === "environment" ? "SET IN ENVIRONMENT · ••••••••" : "No value saved"}</span><input type={field.key === "censys_org_id" ? "text" : "password"} autoComplete="new-password" value={values[index] ?? ""} onChange={(event) => setServiceSecrets((current) => ({ ...current, [service.id]: values.map((value, valueIndex) => valueIndex === index ? event.target.value : value) }))} placeholder={field.credential_source === "missing" ? field.required ? "Enter key" : "Optional" : "Enter a replacement value"} /></label>)}</div>
          <div className="configuration-actions">
            <button disabled={Boolean(busy)} onClick={() => check("service", service.id, values)}>Test</button>
            <button disabled={!values.some(Boolean) || service.credential_fields.some((field, index) => field.required && !values[index] && field.credential_source === "missing") || Boolean(busy)} onClick={async () => { if (await update({ action: "service-credentials", id: service.id, values, verify: true })) setServiceSecrets((current) => ({ ...current, [service.id]: values.map(() => "") })); }}>Save, then test</button>
            {service.credential_fields.some((field) => field.credential_source === "config") && <button className="danger-subtle" onClick={() => update({ action: "remove-service-credentials", id: service.id })}>Remove stored</button>}
            <a href={service.docs_url} target="_blank" rel="noreferrer">Get credential</a>
          </div>
          {serviceOutcome[service.id] && <div className={`configuration-health ${serviceOutcome[service.id].health.state}`} role="status"><b>{serviceOutcome[service.id].saved === true ? "SAVED · " : ""}ACCESS {serviceOutcome[service.id].health.state.toUpperCase()}</b><span>{serviceOutcome[service.id].health.summary}</span></div>}
        </article>;
      })}</div>
    </section>
  </section>;
}

export type ConfigurationAdvisory = {
  character: string;
  character_name: string;
  message: string;
  action: string;
  category: "configuration";
  content_class: "narration";
  evidence: false;
};
