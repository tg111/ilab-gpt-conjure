from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from codex_image.providers.capabilities import CODEC_CAPABILITIES, openai_gif_edit_frame_limit
from codex_image.providers.contracts import (
    ExecutionPlan,
    ProviderConnection,
    ProviderModelBinding,
)
from codex_image.providers.registry import ProviderRegistry

from .capabilities import binding_capabilities
from .parameter_vocabulary import custom_size_error, upgrade_parameters
from .types import GenerationCommand, ModelManifest, ParameterDefinition


class BindingResolver:
    def __init__(
        self,
        *,
        models: Mapping[str, ModelManifest],
        providers: Mapping[str, ProviderConnection],
        registry: ProviderRegistry,
    ) -> None:
        self._models = dict(models)
        self._providers = dict(providers)
        self._registry = registry

    def resolve(self, command: GenerationCommand) -> ExecutionPlan:
        model = self._model(command.canonical_model_id)
        if command.operation not in model.operations:
            raise ValueError(
                f"Model {model.id} does not support operation: {command.operation}"
            )
        validate_command_inputs(command, model)

        provider = self._provider(command.provider_id)
        binding = self._binding(provider, model, command)
        # Submissions may use the earlier vocabulary; validate the unified form.
        parameters = upgrade_parameters(model, command.parameters)
        self._validate_parameters(command.operation, parameters, model)

        # Resolving both declarations here makes missing explicit registrations fail
        # before transport work begins. Protocol execution remains a later boundary.
        self._registry.protocol(binding.protocol_profile)
        self._validate_binding_capabilities(command, parameters, model, binding)
        codec = self._registry.codec(binding.parameter_codec)
        mapped_parameter_ids = codec.mapped_parameter_ids(model, command.operation)
        missing_parameter_ids = sorted(set(parameters) - set(mapped_parameter_ids))
        if missing_parameter_ids:
            raise ValueError(
                "codec_parameter_mapping_missing: " + ", ".join(missing_parameter_ids)
            )

        protocol_request = codec.encode(command, model, binding)
        if binding.parameter_codec == "gpt_openai_images" and protocol_request.path == "/images/edits":
            payload = protocol_request.json_body or {}
            limit = openai_gif_edit_frame_limit(provider.base_url)
            if limit is not None and payload.get("output_format") == "gif" and int(payload.get("frame_count") or 9) > limit:
                raise ValueError("openai_gif_edit_frame_limit_exceeded")
        return ExecutionPlan(
            command=command,
            model=model,
            provider=provider,
            binding=binding,
            protocol_request=protocol_request,
        )

    def _model(self, model_id: str) -> ModelManifest:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise ValueError(f"Unknown image model: {model_id}") from exc

    def _provider(self, provider_id: str) -> ProviderConnection:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ValueError(f"Unknown provider: {provider_id}") from exc

    @staticmethod
    def _binding(
        provider: ProviderConnection,
        model: ModelManifest,
        command: GenerationCommand,
    ) -> ProviderModelBinding:
        model_bindings = tuple(
            binding
            for binding in provider.bindings
            if binding.canonical_model_id == model.id
        )
        if not model_bindings:
            raise ValueError(f"Provider {provider.id} does not support model: {model.id}")

        operation_bindings = tuple(
            binding
            for binding in model_bindings
            if command.operation in binding.operations
        )
        if not operation_bindings:
            raise ValueError(
                f"Provider {provider.id} does not support operation: {command.operation} "
                f"for model: {model.id}"
            )
        if command.binding_id:
            selected = tuple(
                binding for binding in operation_bindings if binding.id == command.binding_id
            )
            if len(selected) != 1:
                raise ValueError(
                    f"Provider {provider.id} does not support binding: {command.binding_id}"
                )
            return selected[0]
        if len(operation_bindings) > 1:
            defaults = tuple(binding for binding in operation_bindings if binding.is_default)
            if len(defaults) == 1:
                return defaults[0]
            raise ValueError(
                "ambiguous provider binding: "
                f"{provider.id}/{model.id}/{command.operation}"
            )
        return operation_bindings[0]

    @classmethod
    def _validate_parameters(
        cls,
        operation: str,
        parameters: Mapping[str, Any],
        model: ModelManifest,
    ) -> None:
        definitions = {definition.id: definition for definition in model.parameters}
        for parameter_id, value in parameters.items():
            try:
                definition = definitions[parameter_id]
            except KeyError as exc:
                raise ValueError(f"Unknown parameter: {parameter_id}") from exc
            if operation not in definition.operations:
                raise ValueError(
                    "Parameter does not support operation: "
                    f"{parameter_id}: {operation}"
                )
            if definition.visible_when and not all(
                cls._condition_matches(condition, parameters, definitions)
                for condition in definition.visible_when
            ):
                raise ValueError(f"Parameter is not applicable: {parameter_id}")
            cls._validate_parameter_value(definition, value)
            for requirement in definition.value_requirements:
                if value == requirement.value and not cls._condition_matches(
                    requirement.condition, parameters, definitions,
                ):
                    raise ValueError(f"{requirement.reason}: {parameter_id}")
        cls._validate_size(parameters, model, definitions)

    @staticmethod
    def _validate_size(parameters, model: ModelManifest, definitions) -> None:
        if model.size_spec is None or "canvas.mode" not in definitions:
            return
        mode = parameters.get("canvas.mode", definitions["canvas.mode"].default)
        if mode != "custom":
            return
        output_format = parameters.get("output.format")
        if output_format is None and "output.format" in definitions:
            output_format = definitions["output.format"].default
        size = parameters.get("canvas.size", definitions["canvas.size"].default)
        error = custom_size_error(model.size_spec, size, output_format)
        if error:
            raise ValueError(f"{error}: canvas.size")

    @staticmethod
    def _validate_binding_capabilities(
        command: GenerationCommand,
        parameters: Mapping[str, Any],
        model: ModelManifest,
        binding: ProviderModelBinding,
    ) -> None:
        if binding.parameter_codec not in CODEC_CAPABILITIES:
            # Codecs registered outside the built-in table declare their own mapping.
            return
        capabilities = binding_capabilities(model, binding.protocol_profile, binding.parameter_codec)
        if not capabilities.available:
            raise ValueError(capabilities.unavailable_reason)
        if command.markup_image and not capabilities.supports_markup:
            raise ValueError("image_feature_requires_openai_images")
        supported = set(capabilities.parameter_ids)
        # A parameter the binding cannot act on is accepted only at its default,
        # where leaving it out would send the same request.
        unsupported = sorted(
            parameter_id
            for parameter_id, value in parameters.items()
            if parameter_id not in supported and value != model.parameter(parameter_id).default
        )
        if unsupported:
            raise ValueError("parameter_not_supported_by_binding: " + ", ".join(unsupported))

    @staticmethod
    def _condition_matches(condition, values, definitions) -> bool:
        reference = definitions.get(condition.parameter_id)
        actual = values.get(condition.parameter_id, reference.default if reference else None)
        if condition.operator == "equals":
            return actual == condition.value
        if condition.operator == "not_equals":
            return actual != condition.value
        return actual in condition.value

    @classmethod
    def _validate_parameter_value(
        cls,
        definition: ParameterDefinition,
        value: Any,
    ) -> None:
        if not cls._has_declared_type(definition.value_type, value):
            raise ValueError(
                f"Invalid parameter type: {definition.id}: expected {definition.value_type}"
            )

        if definition.minimum is not None and value < definition.minimum:
            raise ValueError(
                f"Invalid parameter value: {definition.id}: below minimum {definition.minimum}"
            )
        if definition.maximum is not None and value > definition.maximum:
            raise ValueError(
                f"Invalid parameter value: {definition.id}: above maximum {definition.maximum}"
            )
        if definition.step is not None:
            base = definition.minimum if definition.minimum is not None else 0
            quotient = (value - base) / definition.step
            if not math.isclose(quotient, round(quotient), rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError(
                    f"Invalid parameter value: {definition.id}: invalid step {definition.step}"
                )
        if definition.allowed_values and value not in definition.allowed_values:
            raise ValueError(
                f"Invalid parameter value: {definition.id}: invalid value {value!r}"
            )
        if definition.object_choices and isinstance(value, Mapping):
            choices = {row.key: row for row in definition.object_choices}
            for key, item in value.items():
                row = choices.get(str(key))
                if row is not None and item not in row.allowed_values:
                    raise ValueError(
                        f"Invalid parameter value: {definition.id}.{key}: "
                        f"invalid value {item!r}"
                    )

    @staticmethod
    def _has_declared_type(value_type: str, value: Any) -> bool:
        if value_type == "string":
            return isinstance(value, str)
        if value_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if value_type == "boolean":
            return isinstance(value, bool)
        if value_type == "object":
            return isinstance(value, Mapping)
        return False


def validate_command_inputs(command: GenerationCommand, model: ModelManifest) -> None:
    constraints = model.input_constraints
    if len(command.image_inputs) > constraints.max_images:
        raise ValueError(
            f"image_input_limit_exceeded: maximum {constraints.max_images}"
        )
    if command.mask_image and not constraints.supports_mask:
        raise ValueError("mask_input_unsupported")
    if command.reference_files and not constraints.supports_reference_files:
        raise ValueError("reference_files_unsupported")
    if command.markup_image:
        if not constraints.supports_markup or command.operation != "edit" or not command.image_inputs:
            raise ValueError("markup_requires_supported_image_edit")
        if command.mask_image:
            raise ValueError("markup_cannot_combine_with_mask")
        from codex_image.markup_validation import validate_markup_image
        validate_markup_image(command.markup_image, command.image_inputs[0].data_url)
