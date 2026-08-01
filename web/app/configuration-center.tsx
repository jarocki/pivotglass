"use client";

import { useEffect, useMemo, useState } from "react";

type CredentialSource = "config" | "environment" | "missing" | "not-required";
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
};
type ServiceState = {
  id: string;
  display_name: string;
  enabled: boolean;
  credential_source: CredentialSource;
  credential_fields: Array<{ key: string; label: string }>;
  docs_url: string;
  test_endpoint: string;
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

export function ConfigurationCenter({ onClose }: { onClose: () => void }) {
  const [configuration, setConfiguration] = useState<ConfigurationState | null>(null);
  const [providerId, setProviderId] = useState("");
  const [providerSecret, setProviderSecret] = useState("");
  const [serviceSecrets, setServiceSecrets] = useState<Record<string, string[]>>({});
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [notice, setNotice] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
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
      if (result.health) setHealth(result.health);
      if (result.configuration) setConfiguration(result.configuration);
      else await refresh();
      setNotice(result.saved ? "Configuration saved." : "Nothing was saved; correct the test failure first.");
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
      setHealth(result);
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
    <span className="eyebrow">LOCAL CONTROL · SECRETS STAY OUT OF LOGS AND MODEL PROMPTS</span>
    <h2 id="configuration-heading" tabIndex={-1}>CONFIGURATION</h2>

    <div className="configuration-grid">
      <article className="configuration-section">
        <header><div><h3>AI MODEL</h3><p>{configuration.model.provider_name} · {configuration.model.model}</p></div><span className={`health-state ${configuration.model.enabled ? "ready" : "disabled"}`}>{configuration.model.enabled ? "ENABLED" : "DISABLED"}</span></header>
        <div className="configuration-actions">
          <button onClick={() => update({ action: "model-enabled", enabled: !configuration.model.enabled })}>{configuration.model.enabled ? "DISABLE SYNTHESIS" : "ENABLE SYNTHESIS"}</button>
          <button onClick={() => update({ action: "advisor-enabled", enabled: !configuration.model.advisor_enabled })}>{configuration.model.advisor_enabled ? "DISABLE ADVISOR" : "ENABLE ADVISOR"}</button>
        </div>
        <dl className="configuration-facts">
          <div><dt>Selection source</dt><dd>{configuration.model.source}</dd></div>
          <div><dt>Credential</dt><dd>{configuration.model.credential_source}</dd></div>
          <div><dt>Advisor</dt><dd>{configuration.model.advisor_enabled ? "periodic local suggestions" : "off"}</dd></div>
        </dl>
      </article>

      <article className="configuration-section provider-section">
        <header><div><h3>MODEL PROVIDER</h3><p>Live checks happen only when you request them.</p></div></header>
        <label>Platform<select value={providerId} onChange={(event) => { setProviderId(event.target.value); setModels([]); setHealth(null); }}>{configuration.providers.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
        {provider?.needs_api_key && <label>New credential<input type="password" autoComplete="new-password" value={providerSecret} onChange={(event) => setProviderSecret(event.target.value)} placeholder={provider.credential_source === "missing" ? "Required" : "Leave blank to keep current"} /></label>}
        <p className="credential-note">Credential source: <b>{provider?.credential_source}</b>{provider?.credential_source === "environment" && " · environment-owned values are read-only"}</p>
        <div className="configuration-actions">
          <button disabled={Boolean(busy)} onClick={() => check("provider", providerId)}>{busy === `check-${providerId}` ? "CHECKING…" : "CHECK ACCESS"}</button>
          {provider?.needs_api_key && <button disabled={!providerSecret || Boolean(busy)} onClick={async () => { if (await update({ action: "provider-credential", id: providerId, secret: providerSecret, verify: true })) setProviderSecret(""); }}>SAVE + TEST</button>}
          <button disabled={Boolean(busy)} onClick={loadModels}>{busy === "models" ? "LOADING…" : "VIEW AVAILABLE MODELS"}</button>
          {provider?.credential_source === "config" && <button className="danger-subtle" disabled={Boolean(busy)} onClick={() => update({ action: "remove-provider-credential", id: providerId })}>REMOVE STORED KEY</button>}
        </div>
        <small>Endpoint: {provider?.endpoint}</small>
      </article>
    </div>

    {health && <div className={`configuration-health ${health.state}`} role="status"><b>{health.state.toUpperCase()}</b><span>{health.summary}</span>{health.checked_endpoint && <small>{health.checked_endpoint}</small>}</div>}
    {notice && <p className="configuration-notice" role="status">{notice}</p>}

    {models.length > 0 && <section className="model-catalog" aria-label="Available models">
      <header><h3>AVAILABLE MODELS</h3><span>{models.length} returned by {provider?.display_name}</span></header>
      <div className="model-cards">{models.map((model) => <article key={model.model_id} className={model.runtime_model === configuration.model.model ? "selected" : ""}>
        <header><b>{model.model_id}</b>{model.runtime_model === configuration.model.model && <span>SELECTED</span>}</header>
        <p><strong>Strengths</strong> {model.strengths.join(" ")}</p>
        <p><strong>Limitations</strong> {model.limitations.join(" ")}</p>
        <div className="model-tags">{model.supports_tools && <span>TOOLS</span>}{model.supports_vision && <span>VISION</span>}{model.supports_reasoning && <span>REASONING</span>}{model.context_tokens && <span>{model.context_tokens.toLocaleString()} CONTEXT</span>}</div>
        <button disabled={Boolean(busy) || model.runtime_model === configuration.model.model} onClick={() => update({ action: "select-model", id: providerId, model_id: model.model_id })}>SELECT</button>
      </article>)}</div>
    </section>}

    <section className="service-catalog" aria-label="Intelligence APIs">
      <header><h3>INTELLIGENCE APIS</h3><span>Enable, test, repair, or remove one service at a time</span></header>
      <div>{configuration.services.map((service) => {
        const values = serviceSecrets[service.id] ?? service.credential_fields.map(() => "");
        return <article key={service.id}>
          <header><div><b>{service.display_name}</b><small>{service.credential_source} · {service.test_endpoint}</small></div><button onClick={() => update({ action: "service-enabled", id: service.id, enabled: !service.enabled })}>{service.enabled ? "ENABLED" : "DISABLED"}</button></header>
          <div className="service-credential-fields">{service.credential_fields.map((field, index) => <label key={field.key}>{field.label}<input type="password" autoComplete="new-password" value={values[index] ?? ""} onChange={(event) => setServiceSecrets((current) => ({ ...current, [service.id]: values.map((value, valueIndex) => valueIndex === index ? event.target.value : value) }))} placeholder={service.credential_source === "missing" ? "Required" : "Leave blank to keep current"} /></label>)}</div>
          <div className="configuration-actions">
            <button disabled={Boolean(busy)} onClick={() => check("service", service.id, values)}>TEST</button>
            <button disabled={!values.every(Boolean) || Boolean(busy)} onClick={async () => { if (await update({ action: "service-credentials", id: service.id, values, verify: true })) setServiceSecrets((current) => ({ ...current, [service.id]: values.map(() => "") })); }}>SAVE + TEST</button>
            {service.credential_source === "config" && <button className="danger-subtle" onClick={() => update({ action: "remove-service-credentials", id: service.id })}>REMOVE STORED</button>}
            <a href={service.docs_url} target="_blank" rel="noreferrer">GET CREDENTIAL</a>
          </div>
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
