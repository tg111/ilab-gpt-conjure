"""What one model can do through one provider binding.

Model support lives in the catalog, protocol support in the codec capability
table, and a few protocol rules (GPT Image 2.6 and markup need the Images API,
GPT web search needs a Responses protocol) used to live only inside codec
errors and frontend branches. This module combines the three so the catalog
API and submission validation read the same answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from codex_image.providers.capabilities import CODEC_CAPABILITIES

from .types import ModelManifest

RESPONSES_PROTOCOLS = frozenset({"codex_responses", "openai_responses"})
_IMAGES_API_ONLY_MODEL_PREFIXES = ("gpt-image-2.6-",)
_CODEC_FAMILY_PREFIXES = {"gpt-image": "gpt_", "gemini-image": "gemini_"}
# GPT parameters only a Responses protocol can act on.
_GPT_RESPONSES_ONLY_PARAMETERS = frozenset({"gpt.web_search", "tools.web_search"})


@dataclass(frozen=True)
class BindingCapabilities:
    available: bool
    unavailable_reason: str | None
    parameter_ids: tuple[str, ...]
    uses_main_model: bool
    supports_markup: bool

    def payload(self) -> dict[str, object]:
        return {
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "parameter_ids": list(self.parameter_ids),
            "uses_main_model": self.uses_main_model,
            "supports_markup": self.supports_markup,
        }


def _unavailable(reason: str) -> BindingCapabilities:
    return BindingCapabilities(False, reason, (), False, False)


def binding_capabilities(
    model: ModelManifest,
    protocol_profile: str,
    parameter_codec: str,
) -> BindingCapabilities:
    codec = CODEC_CAPABILITIES.get(parameter_codec)
    if codec is None:
        return _unavailable(f"Unknown parameter codec: {parameter_codec}")
    if protocol_profile not in codec.protocol_profiles:
        return _unavailable(f"codec_protocol_mismatch: {parameter_codec}/{protocol_profile}")
    family_prefix = _CODEC_FAMILY_PREFIXES.get(model.family_id)
    if family_prefix is None or not parameter_codec.startswith(family_prefix):
        return _unavailable(f"codec_family_mismatch: {parameter_codec}/{model.family_id}")
    images_api = protocol_profile == "openai_images"
    if model.id.startswith(_IMAGES_API_ONLY_MODEL_PREFIXES) and not images_api:
        return _unavailable("image_feature_requires_openai_images")
    responses = protocol_profile in RESPONSES_PROTOCOLS
    responses_only = _GPT_RESPONSES_ONLY_PARAMETERS if model.family_id == "gpt-image" and not responses else frozenset()
    parameter_ids = tuple(
        definition.id
        for definition in model.parameters
        if definition.id in codec.mapped_parameter_ids and definition.id not in responses_only
    )
    return BindingCapabilities(
        available=True,
        unavailable_reason=None,
        parameter_ids=parameter_ids,
        uses_main_model=responses,
        supports_markup=model.input_constraints.supports_markup and images_api,
    )


__all__ = ("BindingCapabilities", "RESPONSES_PROTOCOLS", "binding_capabilities")
