"""Unified parameter vocabulary: upgrading old parameters and resolving sizes.

The catalog describes size as ``canvas.mode`` (auto, preset or custom) plus
``canvas.aspect_ratio`` and ``canvas.resolution`` for presets or ``canvas.size``
for custom pixels, and web search as ``tools.web_search``. Earlier submissions
and stored tasks use ``canvas.size`` for every GPT size and per-family web
search ids. ``upgrade_parameters`` rewrites those into the unified vocabulary.
It is idempotent: unified parameters pass through unchanged, so callers can
apply it to anything they read without knowing where it came from.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .catalog import get_model_manifest
from .types import ImageSizeSpec, ModelManifest

_FAMILY_RENAMES = {
    "gpt-image": {"gpt.web_search": "tools.web_search"},
    "gemini-image": {"gemini.google_search": "tools.web_search"},
}
_SIZE_PATTERN = re.compile(r"^(\d+)x(\d+)$")


def _manifest(model: ModelManifest | str) -> ModelManifest:
    return get_model_manifest(model) if isinstance(model, str) else model


def preset_for_size(spec: ImageSizeSpec, size: str) -> tuple[str, str] | None:
    """Return (aspect_ratio, resolution) of the preset with exactly these pixels."""
    for resolution, ratios in spec.presets.items():
        for ratio, (width, height) in ratios.items():
            if f"{width}x{height}" == size:
                return ratio, resolution
    return None


def upgrade_parameters(model: ModelManifest | str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _manifest(model)
    upgraded = dict(parameters)
    defined = {definition.id for definition in manifest.parameters}
    for old, new in _FAMILY_RENAMES.get(manifest.family_id, {}).items():
        # Only rename into a parameter the model has, so an unknown id is still
        # reported under the name the caller sent.
        if old in upgraded and new in defined and new not in upgraded:
            upgraded[new] = upgraded.pop(old)
    spec = manifest.size_spec
    if (
        spec is not None
        and spec.presets
        and "canvas.mode" in defined
        and "canvas.mode" not in upgraded
        and "canvas.size" in upgraded
    ):
        size = upgraded.pop("canvas.size")
        text = str(size).strip()
        preset = preset_for_size(spec, text) if isinstance(size, str) else None
        if isinstance(size, str) and text == "auto":
            upgraded["canvas.mode"] = "auto"
        elif preset is not None:
            upgraded.update({
                "canvas.mode": "preset",
                "canvas.aspect_ratio": preset[0],
                "canvas.resolution": preset[1],
            })
        else:
            upgraded["canvas.mode"] = "custom"
            upgraded["canvas.size"] = size
    return upgraded


def requested_image_size(model: ModelManifest | str, parameters: Mapping[str, Any]) -> Any:
    """The explicit size to send for unified parameters, or None to send none.

    Parameters without ``canvas.mode`` never chose a size, so no size is sent,
    matching requests made before the unified vocabulary.
    """
    manifest = _manifest(model)
    spec = manifest.size_spec
    mode = parameters.get("canvas.mode")
    if spec is None or not spec.presets or mode is None:
        return parameters.get("canvas.size")
    if mode == "auto":
        return "auto"
    if mode == "custom":
        return parameters.get("canvas.size")
    ratio = parameters.get("canvas.aspect_ratio", manifest.parameter("canvas.aspect_ratio").default)
    resolution = parameters.get("canvas.resolution", manifest.parameter("canvas.resolution").default)
    width, height = spec.presets[resolution][ratio]
    return f"{width}x{height}"


def custom_size_error(spec: ImageSizeSpec, size: Any, output_format: str | None) -> str | None:
    """Why custom pixels are not accepted, or None when they are."""
    rules = spec.custom
    if rules is None:
        return "custom_size_unsupported"
    match = _SIZE_PATTERN.match(str(size).strip()) if isinstance(size, str) else None
    if match is None:
        return "custom_size_invalid_format"
    width, height = int(match.group(1)), int(match.group(2))
    if not (rules.min_edge <= width <= rules.max_edge and rules.min_edge <= height <= rules.max_edge):
        return "custom_size_out_of_bounds"
    if width % rules.multiple or height % rules.multiple:
        return "custom_size_not_multiple"
    if output_format in rules.relaxed_formats:
        return None
    if max(width, height) / min(width, height) > rules.max_aspect_ratio:
        return "custom_size_ratio_too_large"
    if not rules.min_pixels <= width * height <= rules.max_pixels:
        return "custom_size_pixels_out_of_range"
    return None


__all__ = (
    "custom_size_error",
    "preset_for_size",
    "requested_image_size",
    "upgrade_parameters",
)
