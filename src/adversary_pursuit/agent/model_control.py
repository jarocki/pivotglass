"""Shared model and API configuration authority.

All user interfaces call this module for model status, live provider catalogues,
selection, credential-safe summaries, health checks, and repair guidance.
Secrets are accepted only by explicit mutation methods and are never returned.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Literal

from adversary_pursuit.agent.provider_setup import (
    CTI_SERVICES,
    PROVIDER_BY_ID,
    PROVIDERS,
    ProviderAuthError,
    ProviderConnectionError,
    _build_model_string,
    _validate_cti_key,
    list_models,
)
from adversary_pursuit.core.config import ConfigManager

HealthState = Literal[
    "ready",
    "disabled",
    "missing",
    "invalid",
    "unreachable",
    "unknown",
]


@dataclass(frozen=True)
class ModelProfile:
    """Safe capability projection for one provider-visible model."""

    model_id: str
    runtime_model: str
    strengths: tuple[str, ...]
    limitations: tuple[str, ...]
    context_tokens: int | None = None
    output_tokens: int | None = None
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_reasoning: bool | None = None
    metadata_source: str = "provider availability plus local capability metadata"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HealthResult:
    """Credential or model endpoint health result."""

    state: HealthState
    summary: str
    checked_endpoint: str | None = None
    available_models: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_provider(model: str | None) -> str | None:
    """Infer a provider only from unambiguous model prefixes or family names."""
    value = (model or "").strip().lower()
    if not value:
        return None
    if value.startswith("openrouter/"):
        return "openrouter"
    if value.startswith("gemini/") or value.startswith("models/gemini"):
        return "google"
    if value.startswith("ollama/"):
        return "ollama"
    if value.startswith("claude"):
        return "anthropic"
    if value.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return None


def _provider_model_id(provider_id: str, runtime_model: str) -> str:
    value = runtime_model
    prefixes = {
        "openrouter": "openrouter/",
        "google": "gemini/",
        "ollama": "ollama/",
    }
    prefix = prefixes.get(provider_id)
    if prefix and value.startswith(prefix):
        value = value[len(prefix) :]
    return value


def _capability_info(runtime_model: str) -> dict[str, Any]:
    """Read optional LiteLLM metadata without making a completion request."""
    try:
        import litellm

        candidates = [
            runtime_model,
            runtime_model.removeprefix("openrouter/"),
            runtime_model.removeprefix("gemini/"),
        ]
        for candidate in candidates:
            info = getattr(litellm, "model_cost", {}).get(candidate)
            if isinstance(info, dict):
                return info
    except Exception:  # noqa: BLE001
        pass
    return {}


def profile_model(provider_id: str, model_id: str) -> ModelProfile:
    """Build evidence-proportional strengths and limitations for a model."""
    provider = PROVIDER_BY_ID[provider_id]
    runtime_model = _build_model_string(provider, model_id)
    info = _capability_info(runtime_model)
    context = info.get("max_input_tokens") or info.get("max_tokens")
    output = info.get("max_output_tokens")
    input_cost = info.get("input_cost_per_token")
    output_cost = info.get("output_cost_per_token")
    supports_tools = info.get("supports_function_calling")
    supports_vision = info.get("supports_vision")
    supports_reasoning = info.get("supports_reasoning")
    mode = info.get("mode")

    strengths: list[str] = []
    limitations: list[str] = []
    if supports_tools is True:
        strengths.append("Structured tool calling is recorded in local capability metadata.")
    elif supports_tools is False:
        limitations.append("Local metadata says structured tool calling is unsupported.")
    if supports_reasoning is True:
        strengths.append("Reasoning-model support is recorded in local capability metadata.")
    if supports_vision is True:
        strengths.append("Vision input support is recorded in local capability metadata.")
    if isinstance(context, int) and context >= 100_000:
        strengths.append(f"Large recorded input context ({context:,} tokens).")
    elif isinstance(context, int):
        limitations.append(f"Recorded input context is {context:,} tokens.")
    if isinstance(input_cost, (int, float)) and isinstance(output_cost, (int, float)):
        if input_cost == 0 and output_cost == 0 and provider_id == "ollama":
            strengths.append("No per-token vendor charge is recorded for local execution.")
            limitations.append("Latency and quality depend on local hardware and the installed model.")
        else:
            limitations.append(
                "Recorded price: "
                f"${input_cost * 1_000_000:.3f} input / "
                f"${output_cost * 1_000_000:.3f} output per million tokens."
            )
    if mode and mode != "chat":
        limitations.append(f"Provider metadata classifies this as {mode}, not chat.")
    if not info:
        limitations.append(
            "Detailed capability metadata is unavailable locally; availability alone "
            "does not prove tool support, quality, quota, or suitability."
        )
    if not strengths:
        strengths.append("The selected provider reports this model as available to the account.")
    limitations.append(
        "Provider listing confirms visibility, not completion quota, latency, or answer quality."
    )
    return ModelProfile(
        model_id=model_id,
        runtime_model=runtime_model,
        strengths=tuple(strengths),
        limitations=tuple(dict.fromkeys(limitations)),
        context_tokens=context if isinstance(context, int) else None,
        output_tokens=output if isinstance(output, int) else None,
        input_cost_per_million=(
            float(input_cost) * 1_000_000
            if isinstance(input_cost, (int, float))
            else None
        ),
        output_cost_per_million=(
            float(output_cost) * 1_000_000
            if isinstance(output_cost, (int, float))
            else None
        ),
        supports_tools=supports_tools if isinstance(supports_tools, bool) else None,
        supports_vision=supports_vision if isinstance(supports_vision, bool) else None,
        supports_reasoning=(
            supports_reasoning if isinstance(supports_reasoning, bool) else None
        ),
    )


class ModelControl:
    """Single authority for provider, model, and API configuration."""

    def __init__(self, config_mgr: ConfigManager) -> None:
        self.config_mgr = config_mgr

    def status(self, runner_model: str | None = None) -> dict[str, Any]:
        env_model = os.environ.get("AP_MODEL")
        config_model = self.config_mgr.get_agent_model()
        effective_model = (
            env_model or config_model or runner_model or "ollama/qwen2.5:8b"
        )
        provider = (
            self.config_mgr.get_agent_provider()
            or infer_provider(effective_model)
            or "ollama"
        )
        if env_model:
            source = "AP_MODEL environment override"
        elif config_model:
            source = "config"
        elif runner_model:
            source = "session"
        else:
            source = "default"
        credential_source = self.config_mgr.get_provider_api_key_source(provider)
        enabled = self.config_mgr.is_agent_enabled()
        configured = bool(effective_model and provider)
        return {
            "enabled": enabled,
            "configured": configured,
            "provider": provider,
            "provider_name": PROVIDER_BY_ID.get(provider, PROVIDERS[-1]).display_name,
            "model": effective_model,
            "model_id": _provider_model_id(provider, effective_model),
            "source": source,
            "credential_source": credential_source,
            "credential_configured": credential_source
            in {"config", "environment", "not-required"},
            "environment_override": bool(env_model),
            "advisor_enabled": self.config_mgr.is_configuration_advisor_enabled(),
        }

    def configuration_summary(self, runner_model: str | None = None) -> dict[str, Any]:
        active = self.status(runner_model)
        providers = [
            {
                "id": provider.id,
                "display_name": provider.display_name,
                "selected": provider.id == active["provider"],
                "needs_api_key": provider.needs_api_key,
                "credential_source": self.config_mgr.get_provider_api_key_source(
                    provider.id
                ),
                "endpoint": provider.list_models_url,
            }
            for provider in PROVIDERS
        ]
        services = []
        for spec in CTI_SERVICES:
            sources = [
                self.config_mgr.get_api_key_source(key) for key in spec.config_keys
            ]
            services.append(
                {
                    "id": spec.id,
                    "display_name": spec.display_name,
                    "enabled": self.config_mgr.is_service_enabled(spec.id),
                    "credential_source": (
                        "config"
                        if "config" in sources
                        else "environment"
                        if "environment" in sources
                        else "missing"
                    ),
                    "credential_fields": [
                        {"key": key, "label": label}
                        for key, label in zip(spec.config_keys, spec.prompt_labels)
                    ],
                    "docs_url": spec.docs_url,
                    "test_endpoint": spec.validate_url.split("?", 1)[0],
                }
            )
        return {
            "model": active,
            "providers": providers,
            "services": services,
        }

    def list_models(
        self, provider_id: str | None = None, api_key: str | None = None
    ) -> list[ModelProfile]:
        status = self.status()
        selected = provider_id or str(status["provider"])
        provider = PROVIDER_BY_ID.get(selected)
        if provider is None:
            raise ValueError(f"Unknown provider: {selected}")
        key = (
            api_key
            if api_key is not None
            else self.config_mgr.get_provider_api_key(selected)
        )
        if provider.needs_api_key and not key:
            raise ValueError(
                f"{provider.display_name} credential is missing. "
                "Open Configuration or set the provider key first."
            )
        model_ids = list_models(provider, key)
        return [profile_model(selected, model_id) for model_id in model_ids]

    def check_provider(
        self, provider_id: str | None = None, api_key: str | None = None
    ) -> HealthResult:
        selected = provider_id or str(self.status()["provider"])
        provider = PROVIDER_BY_ID.get(selected)
        if provider is None:
            return HealthResult("invalid", f"Unknown provider: {selected}")
        try:
            models = self.list_models(selected, api_key)
        except ValueError as exc:
            return HealthResult(
                "missing", str(exc), checked_endpoint=provider.list_models_url
            )
        except ProviderAuthError as exc:
            return HealthResult(
                "invalid", str(exc), checked_endpoint=provider.list_models_url
            )
        except ProviderConnectionError as exc:
            return HealthResult(
                "unreachable", str(exc), checked_endpoint=provider.list_models_url
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                "unknown",
                f"{provider.display_name} returned an unexpected response: {exc}",
                checked_endpoint=provider.list_models_url,
            )
        return HealthResult(
            "ready",
            f"{provider.display_name} accepted the credential and returned "
            f"{len(models)} visible models. Completion quota was not tested.",
            checked_endpoint=provider.list_models_url,
            available_models=len(models),
        )

    def check_service(
        self, service_id: str, values: list[str] | None = None
    ) -> HealthResult:
        spec = next((item for item in CTI_SERVICES if item.id == service_id), None)
        if spec is None:
            return HealthResult("invalid", f"Unknown intelligence service: {service_id}")
        credentials = values or [
            self.config_mgr.get_api_key(key) or "" for key in spec.config_keys
        ]
        if not all(credentials):
            return HealthResult(
                "missing",
                f"{spec.display_name} credential is incomplete.",
                checked_endpoint=spec.validate_url.split("?", 1)[0],
            )
        ok, message = _validate_cti_key(spec, credentials)
        if "timed out" in message.lower() or "network" in message.lower():
            state: HealthState = "unreachable"
        elif ok:
            state = "ready"
        elif "authentication" in message.lower():
            state = "invalid"
        else:
            state = "unknown"
        return HealthResult(
            state,
            message,
            checked_endpoint=spec.validate_url.split("?", 1)[0],
        )

    def select_model(
        self, model_id: str, provider_id: str | None = None
    ) -> dict[str, Any]:
        provider = provider_id or str(self.status()["provider"])
        spec = PROVIDER_BY_ID.get(provider)
        if spec is None:
            raise ValueError(f"Unknown provider: {provider}")
        profiles = self.list_models(provider)
        by_id = {item.model_id: item for item in profiles}
        normalized = _provider_model_id(provider, model_id)
        profile = by_id.get(normalized)
        if profile is None:
            raise ValueError(
                f"{model_id} was not returned by {spec.display_name}. "
                "Run 'model list' to refresh the account-visible catalogue."
            )
        self.config_mgr.set_agent_selection(provider, profile.runtime_model)
        self.config_mgr.set_agent_enabled(True)
        return profile.to_dict()

    def repair_plan(self, runner_model: str | None = None) -> dict[str, Any]:
        status = self.status(runner_model)
        actions: list[dict[str, str]] = []
        if not status["enabled"]:
            actions.append(
                {
                    "severity": "action",
                    "summary": "Model synthesis is disabled.",
                    "command": "model enable",
                }
            )
        if not status["credential_configured"]:
            actions.append(
                {
                    "severity": "error",
                    "summary": f"{status['provider_name']} credential is missing.",
                    "command": "model configure",
                }
            )
        inferred = infer_provider(str(status["model"]))
        configured_provider = self.config_mgr.get_agent_provider()
        if inferred and configured_provider and inferred != configured_provider:
            actions.append(
                {
                    "severity": "warning",
                    "summary": (
                        f"Configured provider {configured_provider} conflicts with "
                        f"the model prefix ({inferred})."
                    ),
                    "command": f"model select {inferred} {status['model_id']}",
                }
            )
        if status["environment_override"]:
            actions.append(
                {
                    "severity": "note",
                    "summary": "AP_MODEL overrides the stored selection for this process.",
                    "command": "unset AP_MODEL",
                }
            )
        if not actions:
            actions.append(
                {
                    "severity": "check",
                    "summary": "Local configuration is coherent. Verify live access next.",
                    "command": "model check",
                }
            )
        return {"status": status, "actions": actions}

    def set_provider_credential(
        self, provider_id: str, secret: str, *, verify: bool = True
    ) -> HealthResult:
        provider = PROVIDER_BY_ID.get(provider_id)
        if provider is None or not provider.needs_api_key:
            raise ValueError(f"Provider does not accept a stored key: {provider_id}")
        if not secret:
            raise ValueError("credential is required")
        result = self.check_provider(provider_id, api_key=secret)
        if verify and result.state != "ready":
            return result
        self.config_mgr.set_provider_api_key(provider_id, secret)
        return result

    def set_service_credentials(
        self,
        service_id: str,
        values: list[str],
        *,
        verify: bool = True,
    ) -> HealthResult:
        spec = next((item for item in CTI_SERVICES if item.id == service_id), None)
        if spec is None:
            raise ValueError(f"Unknown intelligence service: {service_id}")
        if len(values) != len(spec.config_keys) or not all(values):
            raise ValueError("all credential fields are required")
        result = self.check_service(service_id, values)
        if verify and result.state != "ready":
            return result
        for key, value in zip(spec.config_keys, values):
            self.config_mgr.set(f"api_keys.{key}", value)
        return result


def render_model_status(status: dict[str, Any]) -> str:
    """Render scan-friendly model status for terminal surfaces."""
    state = "enabled" if status["enabled"] else "disabled"
    credential = str(status["credential_source"]).replace("-", " ")
    return "\n".join(
        [
            "MODEL CONFIGURATION",
            f"  state      : {state}",
            f"  provider   : {status['provider_name']} ({status['provider']})",
            f"  model      : {status['model']}",
            f"  source     : {status['source']}",
            f"  credential : {credential}",
            f"  advisor    : {'enabled' if status['advisor_enabled'] else 'disabled'}",
        ]
    )


def render_model_catalog(profiles: list[ModelProfile], limit: int = 30) -> str:
    """Render a bounded terminal catalogue with strengths and trade-offs."""
    if not profiles:
        return "The provider returned no models."
    lines = [f"AVAILABLE MODELS ({len(profiles)} visible)"]
    for profile in profiles[:limit]:
        lines.extend(
            [
                "",
                profile.runtime_model,
                f"  strength  : {profile.strengths[0]}",
                f"  trade-off : {profile.limitations[0]}",
            ]
        )
    if len(profiles) > limit:
        lines.append(f"\n… {len(profiles) - limit} additional models available in Configuration.")
    lines.append("\nSelect with: model select <model-id>")
    return "\n".join(lines)


def execute_model_command(
    args: tuple[str, ...] | list[str],
    control: ModelControl,
    runner: Any | None = None,
) -> str:
    """Execute the shared local ``model`` command family."""
    parts = list(args)
    subcommand = parts[0].lower() if parts else "show"
    if subcommand == "show":
        return render_model_status(
            control.status(getattr(runner, "model", None))
        )
    if subcommand in {"list", "catalog"}:
        return render_model_catalog(control.list_models())
    if subcommand == "check":
        selected = control.status(getattr(runner, "model", None))
        provider = str(selected["provider"])
        spec = PROVIDER_BY_ID[provider]
        try:
            profiles = control.list_models(provider)
            visible = {item.runtime_model for item in profiles} | {
                item.model_id for item in profiles
            }
            result = HealthResult(
                "ready",
                f"{spec.display_name} accepted the credential and returned "
                f"{len(profiles)} visible models. Completion quota was not tested.",
                checked_endpoint=spec.list_models_url,
                available_models=len(profiles),
            )
            visibility = (
                "\nSelected model is visible to this account."
                if selected["model"] in visible or selected["model_id"] in visible
                else "\nSelected model was NOT returned by the provider."
            )
        except ValueError as exc:
            result = HealthResult("missing", str(exc), spec.list_models_url)
            visibility = ""
        except ProviderAuthError as exc:
            result = HealthResult("invalid", str(exc), spec.list_models_url)
            visibility = ""
        except ProviderConnectionError as exc:
            result = HealthResult("unreachable", str(exc), spec.list_models_url)
            visibility = ""
        except Exception as exc:  # noqa: BLE001
            result = HealthResult(
                "unknown",
                f"{spec.display_name} returned an unexpected response: {exc}",
                spec.list_models_url,
            )
            visibility = ""
        return (
            f"MODEL CHECK · {result.state.upper()}\n{result.summary}"
            f"\nEndpoint: {result.checked_endpoint or 'unavailable'}{visibility}"
        )
    if subcommand == "select":
        if len(parts) == 1:
            return render_model_catalog(control.list_models())
        provider = None
        model_id = parts[1]
        if len(parts) >= 3 and parts[1].lower() in PROVIDER_BY_ID:
            provider = parts[1].lower()
            model_id = " ".join(parts[2:])
        elif len(parts) > 2:
            model_id = " ".join(parts[1:])
        selected = control.select_model(model_id, provider)
        if runner is not None:
            runner.model = selected["runtime_model"]
        return (
            f"Model selected: {selected['runtime_model']}\n"
            "The provider listing confirms visibility; run 'model check' to "
            "recheck access."
        )
    if subcommand in {"enable", "disable"}:
        enabled = subcommand == "enable"
        control.config_mgr.set_agent_enabled(enabled)
        return (
            "Model-backed synthesis enabled."
            if enabled
            else "Model-backed synthesis disabled. Deterministic tools remain available."
        )
    if subcommand == "advisor":
        if len(parts) != 2 or parts[1].lower() not in {"on", "off"}:
            return "Usage: model advisor on|off"
        enabled = parts[1].lower() == "on"
        control.config_mgr.set_configuration_advisor_enabled(enabled)
        return f"Configuration advisor {'enabled' if enabled else 'disabled'}."
    if subcommand == "repair":
        plan = control.repair_plan(getattr(runner, "model", None))
        lines = ["MODEL REPAIR PLAN"]
        for action in plan["actions"]:
            lines.append(
                f"  {str(action['severity']).upper():7} "
                f"{action['summary']}  →  {action['command']}"
            )
        return "\n".join(lines)
    if subcommand in {"configure", "setup"}:
        return (
            "Open CONFIGURATION in Pivotglass to enter, test, or remove a masked "
            "credential. In a terminal, run 'model list', then "
            "'model select [provider] <model-id>'. Raw keys are intentionally "
            "not accepted on the command line or stored in command history."
        )
    if subcommand == "providers":
        return "\n".join(
            f"{'*' if provider.id == control.status()['provider'] else ' '} "
            f"{provider.id}: {provider.display_name}"
            for provider in PROVIDERS
        )
    return (
        "Usage: model show|providers|list|check|select [provider] <model-id>|"
        "enable|disable|repair|configure|advisor on|off"
    )


def execute_configuration_command(
    args: tuple[str, ...] | list[str], control: ModelControl
) -> str:
    """Execute credential-safe API configuration commands."""
    parts = list(args)
    subcommand = parts[0].lower() if parts else "show"
    if subcommand in {"show", "list"}:
        summary = control.configuration_summary()
        lines = ["INTELLIGENCE API CONFIGURATION"]
        for service in summary["services"]:
            lines.append(
                f"  {'ON ' if service['enabled'] else 'OFF'} "
                f"{service['id']:<14} {service['credential_source']}"
            )
        lines.append(
            "\nCredentials are masked; environment-owned credentials are read-only."
        )
        return "\n".join(lines)
    if subcommand == "check":
        if len(parts) != 2:
            return "Usage: config check <service-id>"
        result = control.check_service(parts[1].lower())
        return (
            f"API CHECK · {parts[1].upper()} · {result.state.upper()}\n"
            f"{result.summary}\nEndpoint: {result.checked_endpoint or 'unavailable'}"
        )
    if subcommand in {"enable", "disable"}:
        if len(parts) != 2:
            return f"Usage: config {subcommand} <service-id>"
        service = parts[1].lower()
        known = {item.id for item in CTI_SERVICES}
        if service not in known:
            return f"Unknown service: {service}. Available: {', '.join(sorted(known))}"
        enabled = subcommand == "enable"
        control.config_mgr.set_service_enabled(service, enabled)
        return f"{service} {'enabled' if enabled else 'disabled'}."
    if subcommand == "repair":
        summary = control.configuration_summary()
        lines = ["API REPAIR PLAN"]
        for service in summary["services"]:
            if not service["enabled"]:
                lines.append(
                    f"  ACTION  {service['display_name']} is disabled → "
                    f"config enable {service['id']}"
                )
            elif service["credential_source"] == "missing":
                lines.append(
                    f"  MISSING {service['display_name']} credential → open CONFIGURATION"
                )
        if len(lines) == 1:
            lines.append(
                "  CHECK   Stored configuration is coherent; test a service with "
                "config check <service-id>."
            )
        return "\n".join(lines)
    if subcommand in {"configure", "setup"}:
        return (
            "Open CONFIGURATION in Pivotglass to enter and test secrets without "
            "placing them in terminal history."
        )
    return "Usage: config show|check <service>|enable <service>|disable <service>|repair|configure"
