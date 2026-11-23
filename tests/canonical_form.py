"""Turn the earlier GPT form fields used in older tests into the canonical submission.

The routes accept only canonical_model_id, provider_id, binding_id and
parameters_json. Requests that used the earlier GPT fields got these defaults,
so converting keeps those tests asserting the same provider requests.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

_PARAMETER_FIELDS = {
    "size": "canvas.size",
    "quality": "gpt.quality",
    "background": "gpt.background",
    "output_format": "output.format",
    "moderation": "gpt.moderation",
    "output_compression": "gpt.output_compression",
    "n": "output.count",
    "web_search": "gpt.web_search",
}
_GPT_DEFAULTS = {
    "canvas.size": "auto",
    "gpt.quality": "low",
    "gpt.background": "auto",
    "output.format": "png",
    "gpt.moderation": "low",
    "output.count": 1,
}
# Display labels and options the unified parameters do not have.
_DROPPED_FIELDS = frozenset({"resolution", "ratio", "orientation", "input_fidelity", "prompt_fidelity", "api_mode"})


def _value(parameter_id: str, value: Any) -> Any:
    if parameter_id in {"output.count", "gpt.output_compression"}:
        return int(value)
    if parameter_id == "gpt.web_search":
        return value is True or str(value).strip().lower() in {"1", "true", "on", "yes"}
    return value


def canonical_form(data: Mapping[str, Any] | Iterable[tuple[str, Any]]) -> Any:
    pairs = list(data.items()) if isinstance(data, Mapping) else list(data)
    keys = {key for key, _ in pairs}
    if "parameters_json" in keys and not keys.intersection(_PARAMETER_FIELDS):
        return data
    single = {key: value for key, value in pairs}
    model_id = str(single.get("model") or single.get("canonical_model_id") or "gpt-image-2")
    parameters: dict[str, Any] = json.loads(single["parameters_json"]) if "parameters_json" in single else {}
    if "parameters_json" not in single and model_id.startswith("gpt-image-"):
        parameters = dict(_GPT_DEFAULTS)
    out: list[tuple[str, Any]] = []
    for key, value in pairs:
        if key in _PARAMETER_FIELDS:
            if value is not None:
                parameters[_PARAMETER_FIELDS[key]] = _value(_PARAMETER_FIELDS[key], value)
        elif key == "model":
            out.append(("canonical_model_id", value))
        elif key == "api_provider_id":
            if "provider_id" not in keys and value:
                out.append(("provider_id", value))
        elif key == "codex_mode":
            if value and "binding_id" not in keys and single.get("provider_id") in (None, "codex"):
                out.append(("binding_id", f"codex-gpt-image-2-{value}"))
        elif key not in _DROPPED_FIELDS and key != "parameters_json":
            out.append((key, value))
    out.append(("parameters_json", json.dumps(parameters)))
    return dict(out) if isinstance(data, Mapping) else out
