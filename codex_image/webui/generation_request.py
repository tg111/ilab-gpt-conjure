from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from codex_image.client_types import ResponsesInputFile
from codex_image.generation.types import GenerationCommand, GenerationOperation, ImageInput
from codex_image.generation.catalog import get_model_manifest, list_model_manifests
from codex_image.generation.parameter_vocabulary import requested_image_size, upgrade_parameters
from codex_image.generation.resolver import BindingResolver
from codex_image.generation.service import GenerationService
from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
from codex_image.providers.registry import default_registry


# Form fields of the earlier GPT-only submission. Requests now carry the model,
# provider and unified parameters; these names are refused so an old client
# learns its options would be ignored instead of silently getting defaults.
REMOVED_FORM_FIELDS = frozenset({
    "model",
    "size",
    "resolution",
    "ratio",
    "orientation",
    "quality",
    "background",
    "output_format",
    "moderation",
    "output_compression",
    "input_fidelity",
    "n",
    "web_search",
    "codex_mode",
    "api_mode",
    "api_provider_id",
})
DEFAULT_CANONICAL_MODEL_ID = "gpt-image-2"


def parse_parameters_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("parameters_json must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("parameters_json must be a JSON object")
    return {str(key): item for key, item in value.items()}


def generation_command_from_form(
    *,
    operation: GenerationOperation,
    canonical_model_id: str,
    provider_id: str,
    parameters: Mapping[str, Any],
    prompt: str,
    image_inputs: tuple[ImageInput, ...] = (),
    reference_files: tuple[ResponsesInputFile, ...] = (),
    mask_image: str | None = None,
    markup_image: str | None = None,
    main_model: str | None = None,
    instructions: str | None = None,
    binding_id: str | None = None,
) -> GenerationCommand:
    return GenerationCommand(
        operation=operation,
        canonical_model_id=canonical_model_id,
        provider_id=provider_id,
        binding_id=binding_id,
        prompt=prompt,
        parameters=dict(parameters),
        image_inputs=image_inputs,
        reference_files=reference_files,
        mask_image=mask_image,
        markup_image=markup_image,
        main_model=main_model,
        instructions=instructions,
    )


def codex_provider_connection(codex_mode: str) -> ProviderConnection:
    del codex_mode
    bindings = tuple(
        ProviderModelBinding(
            id=f"codex-gpt-image-2-{mode}",
            provider_id="codex",
            canonical_model_id="gpt-image-2",
            remote_model_id="gpt-image-2",
            protocol_profile=f"codex_{mode}",
            parameter_codec=f"gpt_codex_{mode}",
            operations=frozenset({"generate", "edit"}),
            is_default=mode == "images",
            transparency_mode="prompt",
        )
        for mode in ("images", "responses")
    )
    return ProviderConnection(
        id="codex",
        name="Codex",
        base_url="https://chatgpt.com/backend-api/codex",
        api_key="",
        concurrency=1,
        bindings=bindings,
        builtin=True,
    )


def preview_generation_command(
    command: GenerationCommand,
    *,
    codex_mode: str,
    provider_connections: list[ProviderConnection],
):
    if command.provider_id == "codex" and not command.binding_id:
        command = replace(command, binding_id=_codex_default_binding_id(codex_mode))
    registry = default_registry()
    resolver = BindingResolver(
        models={model.id: model for model in list_model_manifests()},
        providers=_connections(codex_mode, provider_connections),
        registry=registry,
    )
    return GenerationService(resolver, registry).preview(command)


def _connections(codex_mode: str, provider_connections: list[ProviderConnection]) -> dict[str, ProviderConnection]:
    providers = {provider.id: provider for provider in provider_connections}
    providers["codex"] = codex_provider_connection(codex_mode)
    return providers


def _codex_default_binding_id(codex_mode: str) -> str:
    mode = "responses" if str(codex_mode).strip().lower() == "responses" else "images"
    return f"codex-gpt-image-2-{mode}"


def resolve_submission_binding(
    *,
    operation: GenerationOperation,
    canonical_model_id: str,
    provider_id: str,
    binding_id: str | None,
    codex_mode: str,
    provider_connections: list[ProviderConnection],
) -> ProviderModelBinding:
    """The binding a submission runs on, before any inputs are read; routing follows it."""
    if provider_id == "codex" and not binding_id:
        binding_id = _codex_default_binding_id(codex_mode)
    model = get_model_manifest(canonical_model_id)
    provider = _connections(codex_mode, provider_connections).get(provider_id)
    if provider is None:
        raise ValueError(f"Unknown provider: {provider_id}")
    probe = GenerationCommand(operation, model.id, provider_id, "", {}, binding_id=binding_id)
    return BindingResolver._binding(provider, model, probe)


def _orientation(ratio: str) -> str:
    match = re.fullmatch(r"(\d+):(\d+)", ratio)
    if not match:
        return ""
    width, height = int(match[1]), int(match[2])
    return "square" if width == height else "landscape" if width > height else "portrait"


def _ratio_for_size(size: str) -> str:
    match = re.fullmatch(r"(\d+)x(\d+)", size)
    if not match:
        return ""
    width, height = int(match[1]), int(match[2])
    divisor = math.gcd(width, height) or 1
    return f"{width // divisor}:{height // divisor}"


# Unified parameter ids copied into task params under the names history uses.
_TASK_PARAM_FIELDS = (
    ("gpt.quality", "quality"),
    ("gpt.background", "background"),
    ("output.format", "output_format"),
    ("gpt.moderation", "moderation"),
    ("gpt.output_compression", "output_compression"),
    ("gpt.complexity", "complexity"),
    ("gpt.frame_count", "frame_count"),
    ("gpt.frame_duration_ms", "frame_duration_ms"),
)


def task_params_from_plan(plan: Any, *, main_model: str) -> dict[str, Any]:
    """Task fields shown in history and filters, derived from the resolved request.

    Mirrors the frontend's currentTaskParams so a pending card and its stored task agree.
    """
    parameters = upgrade_parameters(plan.model, plan.command.parameters)
    params: dict[str, Any] = {
        "model": plan.binding.remote_model_id or plan.model.id,
        "n": int(parameters.get("output.count") or 1),
    }
    size = str(requested_image_size(plan.model, parameters) or "")
    if size:
        params["size"] = size
    mode = parameters.get("canvas.mode")
    if mode != "auto":
        ratio = str(parameters.get("canvas.aspect_ratio") or "")
        if mode == "custom":
            ratio = _ratio_for_size(size)
        if ratio:
            params["ratio"] = ratio
            params["orientation"] = _orientation(ratio)
        if mode != "custom" and parameters.get("canvas.resolution"):
            params["resolution"] = parameters["canvas.resolution"]
    for parameter_id, field_name in _TASK_PARAM_FIELDS:
        if parameter_id in parameters:
            params[field_name] = parameters[parameter_id]
    if parameters.get("tools.web_search"):
        params["web_search"] = True
    if main_model:
        params["main_model"] = main_model
    return params


__all__ = (
    "codex_provider_connection",
    "DEFAULT_CANONICAL_MODEL_ID",
    "generation_command_from_form",
    "parse_parameters_json",
    "preview_generation_command",
    "REMOVED_FORM_FIELDS",
    "resolve_submission_binding",
    "task_params_from_plan",
)
