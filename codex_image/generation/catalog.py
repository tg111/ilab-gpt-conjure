from __future__ import annotations

from dataclasses import replace

from .types import (
    CustomSizeRules,
    ImageSizeSpec,
    InputConstraints,
    ModelFamily,
    ModelManifest,
    ObjectChoiceRow,
    ObjectPreset,
    ParameterCondition,
    ParameterDefinition,
    ValueRequirement,
)

MODEL_MANIFEST_VERSION = 1

_ALL_OPERATIONS = frozenset({"generate", "edit"})
_GENERATE_ONLY = frozenset({"generate"})
_NANO_COMMON_ASPECT_RATIOS = (
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
)
_GEMINI_SAFETY_THRESHOLDS = (
    "HARM_BLOCK_THRESHOLD_UNSPECIFIED",
    "OFF",
    "BLOCK_NONE",
    "BLOCK_ONLY_HIGH",
    "BLOCK_MEDIUM_AND_ABOVE",
    "BLOCK_LOW_AND_ABOVE",
)
_GEMINI_SAFETY_THRESHOLD_LABEL_KEYS = (
    "gemini.safety.threshold.unspecified",
    "gemini.safety.threshold.off",
    "gemini.safety.threshold.blockNone",
    "gemini.safety.threshold.blockOnlyHigh",
    "gemini.safety.threshold.blockMediumAndAbove",
    "gemini.safety.threshold.blockLowAndAbove",
)
_GEMINI_SAFETY_CATEGORIES = (
    ("HARM_CATEGORY_HARASSMENT", "gemini.safety.harassment"),
    ("HARM_CATEGORY_HATE_SPEECH", "gemini.safety.hateSpeech"),
    ("HARM_CATEGORY_SEXUALLY_EXPLICIT", "gemini.safety.sexuallyExplicit"),
    ("HARM_CATEGORY_DANGEROUS_CONTENT", "gemini.safety.dangerousContent"),
)
_GEMINI_SAFETY_ROWS = tuple(
    ObjectChoiceRow(
        key=category,
        label_key=label_key,
        default="HARM_BLOCK_THRESHOLD_UNSPECIFIED",
        allowed_values=_GEMINI_SAFETY_THRESHOLDS,
        label_keys=_GEMINI_SAFETY_THRESHOLD_LABEL_KEYS,
    )
    for category, label_key in _GEMINI_SAFETY_CATEGORIES
)
_GEMINI_SAFETY_OFF = {
    category: "OFF" for category, _label_key in _GEMINI_SAFETY_CATEGORIES
}
_GEMINI_SAFETY_BLOCK_ALL = {
    category: "BLOCK_LOW_AND_ABOVE"
    for category, _label_key in _GEMINI_SAFETY_CATEGORIES
}
_GEMINI_SAFETY_PRESETS = (
    ObjectPreset(
        id="off",
        label_key="gemini.safety.threshold.off",
        value=_GEMINI_SAFETY_OFF,
        matches_empty=True,
    ),
    ObjectPreset(
        id="block_all",
        label_key="gemini.safety.threshold.blockLowAndAbove",
        value=_GEMINI_SAFETY_BLOCK_ALL,
    ),
)

MODEL_FAMILIES = (
    ModelFamily("gpt-image", "GPT Image", "GPT", "modelFamily.gptImage"),
    ModelFamily("gemini-image", "Gemini", "Gemini", "modelFamily.gemini"),
)


def _output_count(maximum: int = 4, *, control: str = "number") -> ParameterDefinition:
    return ParameterDefinition(
        id="output.count",
        label_key="output.quantity",
        group="generation",
        control=control,
        value_type="integer",
        default=1,
        allowed_values=tuple(range(1, maximum + 1)) if control == "segmented" else (),
        scope="application",
        minimum=1,
        maximum=maximum,
        step=1,
    )


def _select(
    parameter_id: str,
    label_key: str,
    group: str,
    default: str,
    allowed_values: tuple[str, ...],
    *,
    control: str = "select",
    full_width: bool = False,
) -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control=control,
        value_type="string",
        default=default,
        allowed_values=allowed_values,
        full_width=full_width,
    )


def _toggle(parameter_id: str, label_key: str, *, group: str = "advanced") -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control="toggle",
        value_type="boolean",
        default=False,
    )


def _boolean_segmented(
    parameter_id: str,
    label_key: str,
    *,
    group: str = "advanced",
) -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control="boolean_segmented",
        value_type="boolean",
        default=False,
    )


def _object_presets(
    parameter_id: str,
    label_key: str,
    rows: tuple[ObjectChoiceRow, ...],
    presets: tuple[ObjectPreset, ...],
    default: dict[str, str],
    *,
    group: str = "advanced",
    full_width: bool = True,
) -> ParameterDefinition:
    return ParameterDefinition(
        id=parameter_id,
        label_key=label_key,
        group=group,
        control="object_presets",
        value_type="object",
        default=default,
        full_width=full_width,
        object_choices=rows,
        object_presets=presets,
    )


def _nano_parameters(
    resolutions: tuple[str, ...],
    aspect_ratios: tuple[str, ...],
    *,
    google_search: bool,
) -> tuple[ParameterDefinition, ...]:
    parameters = [
        _select(
            "canvas.aspect_ratio",
            "canvas.aspectRatio",
            "canvas",
            "1:1",
            aspect_ratios,
            control="aspect_ratio_grid",
            full_width=True,
        ),
        _select(
            "canvas.resolution",
            "canvas.resolution",
            "canvas",
            "1K",
            resolutions,
            control="segmented",
        ),
        _output_count(control="segmented"),
        _object_presets(
            "gemini.safety_settings",
            "gemini.safetySettings",
            _GEMINI_SAFETY_ROWS,
            _GEMINI_SAFETY_PRESETS,
            _GEMINI_SAFETY_OFF,
            group="generation",
            full_width=False,
        ),
    ]
    if google_search:
        parameters.append(
            _boolean_segmented(
                "gemini.google_search",
                "gemini.googleSearch",
                group="generation",
            )
        )
    return tuple(parameters)


MODEL_MANIFESTS = (
    ModelManifest(
        id="gpt-image-2",
        family_id="gpt-image",
        display_name="GPT Image 2",
        official_model_id="gpt-image-2",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=(
            # Empty allowed_values permits custom sizes only after the GPT-specific
            # size validator applies the compound dimension rules (Task 9 boundary).
            ParameterDefinition(
                id="canvas.size",
                label_key="output.size",
                group="canvas",
                control="text",
                value_type="string",
                default="1024x1024",
                full_width=True,
            ),
            _select(
                "gpt.quality",
                "output.quality",
                "generation",
                "auto",
                ("auto", "low", "medium", "high"),
                control="segmented",
            ),
            _select(
                "gpt.background",
                "output.background",
                "generation",
                "auto",
                ("auto", "transparent", "opaque"),
                control="segmented",
            ),
            _select(
                "output.format",
                "output.format",
                "generation",
                "png",
                ("png", "jpeg", "webp"),
                control="segmented",
            ),
            _select(
                "gpt.moderation",
                "output.moderation",
                "generation",
                "low",
                ("auto", "low"),
                control="segmented",
            ),
            ParameterDefinition(
                id="gpt.output_compression",
                label_key="output.compression",
                group="advanced",
                control="slider",
                value_type="integer",
                default=80,
                minimum=0,
                maximum=100,
                step=1,
                visible_when=(ParameterCondition("output.format", "in", ("jpeg", "webp")),),
            ),
            _toggle("gpt.web_search", "output.webSearch"),
            _output_count(),
        ),
        input_constraints=InputConstraints(
            max_images=16,
            supports_mask=True,
            supports_reference_files=True,
        ),
    ),
    ModelManifest(
        id="nano-banana-pro",
        family_id="gemini-image",
        display_name="Nano Banana Pro",
        official_model_id="gemini-3-pro-image",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=_nano_parameters(
            ("1K", "2K", "4K"),
            _NANO_COMMON_ASPECT_RATIOS,
            google_search=True,
        ),
        input_constraints=InputConstraints(
            max_images=14,
            supports_mask=False,
            supports_reference_files=False,
        ),
        expand_advanced_parameters=True,
    ),
    ModelManifest(
        id="nano-banana-2.1",
        family_id="gemini-image",
        display_name="Nano Banana 2.1",
        official_model_id="gemini-nano-banana-2.1",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=_nano_parameters(
            ("1K", "2K", "4K"),
            _NANO_COMMON_ASPECT_RATIOS + ("1:4", "1:8", "4:1", "8:1"),
            google_search=True,
        ),
        input_constraints=InputConstraints(
            max_images=14,
            supports_mask=False,
            supports_reference_files=False,
        ),
        expand_advanced_parameters=True,
    ),
    ModelManifest(
        id="nano-banana-2",
        family_id="gemini-image",
        display_name="Nano Banana 2",
        official_model_id="gemini-3.1-flash-image",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=_nano_parameters(
            ("512", "1K", "2K", "4K"),
            _NANO_COMMON_ASPECT_RATIOS + ("1:4", "1:8", "4:1", "8:1"),
            google_search=True,
        ),
        input_constraints=InputConstraints(
            max_images=14,
            supports_mask=False,
            supports_reference_files=False,
        ),
        expand_advanced_parameters=True,
    ),
    ModelManifest(
        id="nano-banana-2-lite",
        family_id="gemini-image",
        display_name="Nano Banana 2 Lite",
        official_model_id="gemini-3.1-flash-lite-image",
        version=MODEL_MANIFEST_VERSION,
        operations=_ALL_OPERATIONS,
        parameters=_nano_parameters(
            ("1K",),
            _NANO_COMMON_ASPECT_RATIOS,
            google_search=False,
        ),
        input_constraints=InputConstraints(
            max_images=14,
            supports_mask=False,
            supports_reference_files=False,
        ),
        expand_advanced_parameters=True,
    ),
)

# Keep the original model's contract stable for Codex and existing snapshots.
GPT_IMAGE_26_MODEL_IDS = frozenset({"gpt-image-2.6-flare", "gpt-image-2.6-sunburst"})
GPT_IMAGE_MODEL_IDS = frozenset({"gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"}) | GPT_IMAGE_26_MODEL_IDS


def _gpt_version_parameters(version: str) -> tuple[ParameterDefinition, ...]:
    parameters = tuple(
        replace(parameter, allowed_values=("auto", "low", "medium", "high", "xhigh", "max"))
        if parameter.id == "gpt.quality" else
        replace(parameter, allowed_values=("png", "jpeg", "webp", "svg", "gif"))
        if parameter.id == "output.format" and version == "2.6" else parameter
        for parameter in MODEL_MANIFESTS[0].parameters
    )
    if version == "2.6":
        parameters += (
            _select("gpt.complexity", "output.complexity", "generation", "high",
                    ("low", "medium", "high"), control="segmented"),
            ParameterDefinition(
                id="gpt.frame_count", label_key="output.frameCount", group="advanced",
                control="number", value_type="integer", default=9, minimum=2, maximum=64, step=1,
                visible_when=(ParameterCondition("output.format", "equals", "gif"),),
            ),
            ParameterDefinition(
                id="gpt.frame_duration_ms", label_key="output.frameDuration", group="advanced",
                control="number", value_type="integer", default=200, minimum=20, maximum=2000, step=10,
                visible_when=(ParameterCondition("output.format", "equals", "gif"),),
            ),
        )
    return parameters


_LEGACY_MANIFESTS = (MODEL_MANIFESTS[0], *(
    replace(MODEL_MANIFESTS[0], id=f"gpt-image-{version}-{variant}",
            official_model_id=f"gpt-image-{version}-{variant}",
            display_name=f"GPT Image {version} {variant.title()}",
            parameters=_gpt_version_parameters(version),
            input_constraints=replace(MODEL_MANIFESTS[0].input_constraints, supports_markup=True))
    for version in ("2.5", "2.6") for variant in ("flare", "sunburst")
), *MODEL_MANIFESTS[1:])


# Unified parameter vocabulary ------------------------------------------------
# Size is chosen through canvas.mode (auto, preset, custom); a preset is an
# aspect ratio plus a resolution; custom pixels go in canvas.size. Web search is
# tools.web_search for every family. Other parameters keep their ids.

GPT_SIZE_PRESETS: dict[str, dict[str, tuple[int, int]]] = {
    "1K": {
        "1:1": (1024, 1024), "4:5": (1024, 1280), "5:4": (1280, 1024),
        "3:4": (1152, 1536), "4:3": (1536, 1152), "2:3": (1024, 1536),
        "3:2": (1536, 1024), "9:16": (864, 1536), "16:9": (1536, 864),
        "9:21": (672, 1568), "21:9": (1568, 672),
    },
    "2K": {
        "1:1": (2048, 2048), "4:5": (1600, 2000), "5:4": (2000, 1600),
        "3:4": (1536, 2048), "4:3": (2048, 1536), "2:3": (1344, 2016),
        "3:2": (2016, 1344), "9:16": (1152, 2048), "16:9": (2048, 1152),
        "9:21": (1152, 2688), "21:9": (2688, 1152),
    },
    "4K": {
        "1:1": (2880, 2880), "4:5": (2560, 3200), "5:4": (3200, 2560),
        "3:4": (2448, 3264), "4:3": (3264, 2448), "2:3": (2336, 3504),
        "3:2": (3504, 2336), "9:16": (2160, 3840), "16:9": (3840, 2160),
        "9:21": (1632, 3808), "21:9": (3808, 1632),
    },
}
GPT_ASPECT_RATIOS = tuple(GPT_SIZE_PRESETS["1K"])
GPT_CUSTOM_SIZE_RULES = CustomSizeRules(
    min_edge=16,
    max_edge=3840,
    multiple=16,
    max_aspect_ratio=3,
    min_pixels=655_360,
    max_pixels=8_294_400,
    relaxed_formats=("gif",),
)
GPT_SIZE_SPEC = ImageSizeSpec(
    modes=("auto", "preset", "custom"),
    presets=GPT_SIZE_PRESETS,
    custom=GPT_CUSTOM_SIZE_RULES,
)
PROVIDER_SIZED_SPEC = ImageSizeSpec(modes=("preset",))
TRANSPARENT_FORMATS = ("png", "webp", "svg")

_PRESET_ONLY = (ParameterCondition("canvas.mode", "equals", "preset"),)


_VALUE_LABEL_KEYS = {
    "canvas.mode": {"auto": "output.sizeAuto", "preset": "output.sizePreset", "custom": "output.sizeCustom"},
    "gpt.quality": {
        "auto": "output.qualityAuto", "low": "output.qualityLow", "medium": "output.qualityMedium",
        "high": "output.qualityHigh", "xhigh": "output.qualityXhigh", "max": "output.qualityMax",
    },
    "gpt.complexity": {"low": "output.qualityLow", "medium": "output.qualityMedium", "high": "output.qualityHigh"},
    "gpt.moderation": {"auto": "ux.moderationAuto", "low": "ux.moderationLow"},
    "gpt.background": {
        "auto": "output.backgroundAuto", "transparent": "output.backgroundTransparent",
        "opaque": "output.backgroundOpaque",
    },
}


def _labelled(definition: ParameterDefinition) -> ParameterDefinition:
    labels = _VALUE_LABEL_KEYS.get(definition.id)
    if not labels:
        return definition
    return replace(definition, value_label_keys=tuple(labels[str(value)] for value in definition.allowed_values))


def _canvas_mode(modes: tuple[str, ...]) -> ParameterDefinition:
    return _labelled(ParameterDefinition(
        id="canvas.mode",
        label_key="output.size",
        group="canvas",
        control="image_size",
        value_type="string",
        default="preset",
        allowed_values=modes,
        full_width=True,
    ))


def _web_search(label_key: str) -> ParameterDefinition:
    # A segmented off/on control matches the height of its neighbours. Tools sit
    # beside the main model when the binding uses one, as search always has.
    return _boolean_segmented("tools.web_search", label_key, group="tools")


def _unified_gpt_parameters(legacy: tuple[ParameterDefinition, ...]) -> tuple[ParameterDefinition, ...]:
    parameters: list[ParameterDefinition] = []
    for definition in legacy:
        if definition.id == "canvas.size":
            parameters += [
                _canvas_mode(GPT_SIZE_SPEC.modes),
                replace(
                    _select("canvas.aspect_ratio", "canvas.aspectRatio", "canvas", "1:1",
                            GPT_ASPECT_RATIOS, control="aspect_ratio_grid", full_width=True),
                    visible_when=_PRESET_ONLY,
                ),
                replace(
                    _select("canvas.resolution", "canvas.resolution", "canvas", "1K",
                            tuple(GPT_SIZE_PRESETS), control="segmented"),
                    visible_when=_PRESET_ONLY,
                ),
                replace(definition, control="pixel_size",
                        visible_when=(ParameterCondition("canvas.mode", "equals", "custom"),)),
            ]
        elif definition.id == "gpt.background":
            parameters.append(replace(_labelled(definition), value_requirements=(
                ValueRequirement(
                    "transparent",
                    ParameterCondition("output.format", "in", TRANSPARENT_FORMATS),
                    "transparent_background_requires_png_webp_or_svg",
                ),
            )))
        elif definition.id == "gpt.web_search":
            parameters.append(_web_search(definition.label_key))
        elif definition.id == "output.count":
            # One count control for every family.
            parameters.append(_output_count(control="segmented"))
        else:
            parameters.append(_labelled(definition))
    order = {parameter_id: index for index, parameter_id in enumerate(_GPT_PARAMETER_ORDER)}
    return tuple(sorted(parameters, key=lambda definition: order.get(definition.id, len(order))))


# Main-area fields first in reading order, then the advanced options.
_GPT_PARAMETER_ORDER = (
    "canvas.mode", "canvas.aspect_ratio", "canvas.resolution", "canvas.size",
    "gpt.quality", "gpt.complexity", "output.count", "output.format", "gpt.background",
    "gpt.moderation", "tools.web_search", "gpt.output_compression",
    "gpt.frame_count", "gpt.frame_duration_ms",
)


def _unified_gemini_parameters(legacy: tuple[ParameterDefinition, ...]) -> tuple[ParameterDefinition, ...]:
    parameters: list[ParameterDefinition] = [_canvas_mode(PROVIDER_SIZED_SPEC.modes)]
    for definition in legacy:
        if definition.id in ("canvas.aspect_ratio", "canvas.resolution"):
            parameters.append(replace(definition, visible_when=_PRESET_ONLY))
        elif definition.id == "gemini.google_search":
            parameters.append(_web_search(definition.label_key))
        else:
            parameters.append(definition)
    return tuple(parameters)


def _unified_manifest(legacy: ModelManifest) -> ModelManifest:
    gpt = legacy.family_id == "gpt-image"
    return replace(
        legacy,
        parameters=(_unified_gpt_parameters if gpt else _unified_gemini_parameters)(legacy.parameters),
        size_spec=GPT_SIZE_SPEC if gpt else PROVIDER_SIZED_SPEC,
    )


MODEL_MANIFESTS = tuple(_unified_manifest(model) for model in _LEGACY_MANIFESTS)

MODEL_MANIFESTS_BY_ID = {model.id: model for model in MODEL_MANIFESTS}


def list_model_families() -> tuple[ModelFamily, ...]:
    return MODEL_FAMILIES


def list_model_manifests() -> tuple[ModelManifest, ...]:
    return MODEL_MANIFESTS


def get_model_manifest(model_id: str) -> ModelManifest:
    try:
        return MODEL_MANIFESTS_BY_ID[model_id]
    except KeyError as exc:
        raise KeyError(f"Unknown image model: {model_id}") from exc


def manifests_for_family(family_id: str) -> tuple[ModelManifest, ...]:
    return tuple(model for model in MODEL_MANIFESTS if model.family_id == family_id)
