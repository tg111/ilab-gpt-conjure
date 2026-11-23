from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI

from codex_image.generation.capabilities import binding_capabilities
from codex_image.generation.parameter_vocabulary import FAMILY_PARAMETER_RENAMES
from codex_image.generation.catalog import (
    MODEL_MANIFEST_VERSION,
    list_model_families,
    list_model_manifests,
)
from codex_image.providers.capabilities import openai_gif_edit_frame_limit
from codex_image.providers.registry import default_registry
from codex_image.providers.transparency import transparency_instruction
from codex_image.webui.context import WebUIContext


def _runtime_available(profile: str, codec: str) -> bool:
    registry = default_registry()
    try:
        registry.protocol(profile)
        registry.codec(codec)
    except ValueError:
        return False
    return True


def _with_capabilities(binding: dict[str, Any], models: dict[str, Any]) -> dict[str, Any]:
    model = models.get(str(binding.get("canonical_model_id") or ""))
    if model is not None:
        binding["capabilities"] = binding_capabilities(
            model,
            str(binding.get("protocol_profile") or ""),
            str(binding.get("parameter_codec") or ""),
        ).payload()
    return binding


def _parameter_payload(parameter: Any) -> dict[str, Any]:
    payload = asdict(parameter)
    payload["allowed_values"] = list(parameter.allowed_values)
    payload["operations"] = sorted(parameter.operations)
    payload["visible_when"] = [asdict(condition) for condition in parameter.visible_when]
    if parameter.value_requirements:
        payload["value_requirements"] = [asdict(requirement) for requirement in parameter.value_requirements]
    else:
        payload.pop("value_requirements", None)
    payload["object_choices"] = [
        {
            **asdict(row),
            "allowed_values": list(row.allowed_values),
            "label_keys": list(row.label_keys),
        }
        for row in parameter.object_choices
    ]
    payload["object_presets"] = [
        {
            "id": preset.id,
            "label_key": preset.label_key,
            "value": dict(preset.value),
            "matches_empty": preset.matches_empty,
        }
        for preset in parameter.object_presets
    ]
    return payload


def _size_spec_payload(spec: Any) -> dict[str, Any] | None:
    if spec is None:
        return None
    return {
        "modes": list(spec.modes),
        "presets": {
            resolution: {ratio: list(pixels) for ratio, pixels in ratios.items()}
            for resolution, ratios in spec.presets.items()
        },
        "custom": asdict(spec.custom) if spec.custom is not None else None,
    }


def _model_payload(model: Any) -> dict[str, Any]:
    # "parameters" keeps the vocabulary of the current form; the unified form
    # reads "unified_parameters" and "size_spec".
    legacy = model.legacy_parameters or model.parameters
    return {
        "id": model.id,
        "family_id": model.family_id,
        "display_name": model.display_name,
        "official_model_id": model.official_model_id,
        "version": model.version,
        "operations": sorted(model.operations),
        "parameters": [_parameter_payload(parameter) for parameter in legacy],
        "unified_parameters": [_parameter_payload(parameter) for parameter in model.parameters],
        "size_spec": _size_spec_payload(model.size_spec),
        "input_constraints": asdict(model.input_constraints),
        "expand_advanced_parameters": model.expand_advanced_parameters,
    }


def generation_catalog_payload(ctx: WebUIContext) -> dict[str, Any]:
    settings = ctx.api_settings.public_settings()
    codex_mode = str(settings.get("codex_mode") or "images")
    codex_available = bool(ctx.route_helpers["codex_auth_checker"]())
    models = {model.id: model for model in list_model_manifests()}
    codex_bindings = [
        {
            "id": f"codex-gpt-image-2-{mode}",
            "canonical_model_id": "gpt-image-2",
            "remote_model_id": "gpt-image-2",
            "protocol_profile": f"codex_{mode}",
            "parameter_codec": f"gpt_codex_{mode}",
            "transparency_mode": "prompt",
            "transparency_instruction": transparency_instruction(),
            "operations": ["edit", "generate"],
            "display_name": "Codex Responses" if mode == "responses" else "Codex Image",
        }
        for mode in ("images", "responses")
    ]
    codex_bindings = [_with_capabilities(binding, models) for binding in codex_bindings]
    providers: list[dict[str, Any]] = [{
        "id": "codex",
        "name": "Codex",
        "builtin": True,
        "available": codex_available,
        "api_key_set": codex_available,
        "concurrency": 1,
        "bindings": codex_bindings,
    }]
    for provider in settings.get("providers") or []:
        bindings = []
        for raw_binding in provider.get("bindings") or []:
            binding = dict(raw_binding)
            if binding.get("transparency_mode") == "prompt":
                binding["transparency_instruction"] = transparency_instruction()
            binding["available"] = _runtime_available(
                str(binding.get("protocol_profile") or ""),
                str(binding.get("parameter_codec") or ""),
            )
            bindings.append(_with_capabilities(binding, models))
        runtime_available = any(binding["available"] for binding in bindings)
        catalog_provider = {
            "id": provider["id"],
            "name": provider["name"],
            "builtin": False,
            "available": bool(provider.get("api_key_set")) and runtime_available,
            "api_key_set": bool(provider.get("api_key_set")),
            "base_url": provider.get("base_url", ""),
            "concurrency": provider.get("concurrency", 1),
            "bindings": bindings,
        }
        icon_emoji = str(provider.get("icon_emoji") or "").strip()
        gif_frame_limit = openai_gif_edit_frame_limit(catalog_provider["base_url"])
        if gif_frame_limit is not None:
            catalog_provider["gif_edit_max_frames"] = gif_frame_limit
        if icon_emoji:
            catalog_provider["icon_emoji"] = icon_emoji
        providers.append(catalog_provider)
    return {
        "schema_version": 1,
        "manifest_version": MODEL_MANIFEST_VERSION,
        "families": [asdict(family) for family in list_model_families()],
        "models": [_model_payload(model) for model in models.values()],
        "providers": providers,
        # Earlier parameter names per family; the unified form upgrades stored
        # drafts, locks and history with the same rules the backend applies.
        "parameter_renames": {family: dict(renames) for family, renames in FAMILY_PARAMETER_RENAMES.items()},
        "default_provider_by_model": dict(settings.get("default_provider_by_model") or {}),
        "codex": {"available": codex_available, "mode": codex_mode},
    }


def register_generation_catalog_routes(app: FastAPI, ctx: WebUIContext) -> None:
    @app.get("/api/generation-catalog")
    def generation_catalog() -> dict[str, Any]:
        return generation_catalog_payload(ctx)


__all__ = ("generation_catalog_payload", "register_generation_catalog_routes")
