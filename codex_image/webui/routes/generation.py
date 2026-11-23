from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from codex_image.client import DEFAULT_MAIN_MODEL
from codex_image.generation.capabilities import RESPONSES_PROTOCOLS, binding_capabilities
from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.snapshot import generation_snapshot
from codex_image.generation.service import redacted_protocol_request
from codex_image.client_types import ResponsesInputFile
from codex_image.generation.types import ImageInput
from codex_image.webui.context import WebUIContext
from codex_image.webui.gallery_prompt import resolve_gallery_prompt
from codex_image.webui.prompt_image_mentions import resolve_prompt_image_mentions
from codex_image.webui.auth_routing import (
    BACKEND_CODEX_IMAGES,
    BACKEND_CODEX_RESPONSES,
    BACKEND_OPENAI_IMAGES,
    BACKEND_OPENAI_RESPONSES,
)
from codex_image.webui.generation_request import (
    DEFAULT_CANONICAL_MODEL_ID,
    REMOVED_FORM_FIELDS,
    generation_command_from_form,
    parse_parameters_json,
    preview_generation_command,
    resolve_submission_binding,
    task_params_from_plan,
)
from codex_image.webui.image_uploads import (
    InvalidRasterImage,
    ValidatedRasterImage,
    read_validated_raster_uploads,
)
from codex_image.webui.resource_limits import (
    MAX_TASK_IMAGE_BYTES,
    TaskImageLimitError,
    TaskImageResource,
    validate_task_image_total,
)
from codex_image.webui.executor import (
    _file_to_data_url,
    _resolve_gallery_refs,
    _resolve_reference_assets,
)
from codex_image.webui.executor_inputs import (
    _bytes_to_data_url,
    _reference_file_to_responses_input,
    _resolve_reference_files,
)
from codex_image.webui.reference_file_capabilities import (
    effective_reference_file_main_model,
    reference_file_capability_key_for_backend,
)
from codex_image.webui.reference_files import (
    ReferenceFileStorage,
    ValidatedReferenceFile,
    dedupe_reference_file_records,
    read_reference_file_uploads,
    reference_file_task_record,
    resolve_reference_file_ids,
    validate_reference_file_total,
)
from codex_image.webui.reference_image_order import (
    normalize_reference_image_order,
    ordered_reference_data_urls,
)
from codex_image.webui.storage import utc_now
from codex_image.webui.task_metadata import _dedupe_preserve_order, _with_file_urls, _write_queued_metadata

REFERENCE_FILE_ERROR_MESSAGES = {
    "reference_file_empty": "Reference files cannot be empty.",
    "reference_file_type_unsupported": "This reference file type is not supported.",
    "reference_file_type_mismatch": "The reference file type does not match its filename.",
    "reference_file_invalid": "The reference file is invalid.",
    "reference_file_too_large": "The reference file is too large.",
    "reference_files_total_too_large": "The combined reference files are too large.",
}
REFERENCE_FILE_MISSING_DETAIL = {
    "code": "reference_file_missing",
    "message": "A referenced file is no longer available.",
}
PROVIDER_REFERENCE_FILES_UNSUPPORTED_DETAIL = {
    "code": "provider_reference_files_unsupported",
    "message": "This provider does not support reference files for the selected Responses model.",
}
TASK_IMAGES_TOTAL_TOO_LARGE_DETAIL = {
    "code": "task_images_total_too_large",
    "message": "The combined task images are too large.",
}

LEGACY_FORM_FIELDS_REMOVED_MESSAGE = (
    "These form fields are no longer accepted: {fields}. Send canonical_model_id, "
    "provider_id and parameters_json (unified parameter ids) instead."
)


@dataclass(frozen=True)
class PreparedReferenceFiles:
    uploads: tuple[ValidatedReferenceFile, ...]
    selected_asset_ids: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    response_inputs: tuple[ResponsesInputFile, ...]


@dataclass(frozen=True)
class SubmissionRouting:
    """Where a submission runs, decided by the selected binding before inputs are read."""

    auth_source: str
    canonical_model_id: str
    provider_id: str
    binding_id: str
    parameters: dict[str, Any]
    requested_backend: str
    api_mode: str | None
    codex_mode: str | None
    api_provider_id: str | None
    api_provider_name: str | None
    api_images_concurrency: int
    uses_main_model: bool


@dataclass(frozen=True)
class PreparedGenerationSubmission:
    plan: Any
    request_payload: dict[str, Any]
    model_prompt: str
    prompt_constraints: Any
    params: dict[str, Any]
    prompt_locale: str


def _request_auth_source(ctx: WebUIContext, provider_id: str | None) -> str:
    explicit = str(provider_id or "").strip()
    if explicit:
        return "codex" if explicit == "codex" else "api"
    if ctx.route_helpers["client_factory_overridden"]:
        return "codex"
    return ctx.auth_settings.read_source()


_CUSTOM_SIZE_MESSAGES = {
    "custom_size_invalid_format": "Custom sizes are written as WIDTHxHEIGHT, for example 1536x1024.",
    "custom_size_out_of_bounds": "Each custom size edge must be within the model's limits.",
    "custom_size_not_multiple": "Custom size edges must be multiples of the model's step.",
    "custom_size_ratio_too_large": "The custom size is too wide or too tall for this model.",
    "custom_size_pixels_out_of_range": "The custom size has too few or too many pixels for this model.",
}


def _generation_request_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    format_errors = {
        "openai_gif_edit_frame_limit_exceeded": "OpenAI GIF edits support up to 16 frames. Reduce the frame count.",
        "gif_output_does_not_support_mask": "GIF output does not support masks. Remove the mask or choose another output format.",
        "gif_output_does_not_support_compression": "GIF output does not support compression settings. Remove compression or choose JPEG/WebP.",
        "gif_output_does_not_support_partial_images": "GIF output does not support partial-image previews. Disable partial-image previews or choose another output format.",
        "output_compression_requires_jpeg_or_webp": "Compression settings require JPEG or WebP output. Remove compression or choose JPEG/WebP.",
    }
    if message == "Parameter is not applicable: gpt.output_compression":
        message = "output_compression_requires_jpeg_or_webp"
    if message in format_errors:
        code = message
        safe_message = format_errors[message]
    elif message == "gif_frame_pixel_limit_exceeded":
        code = message
        safe_message = "Reduce GIF frame count or resolution to stay within the local image decoding limit."
    elif message == "transparent_background_requires_png_or_webp" or message.startswith(
        "transparent_background_requires_png_webp_or_svg:"
    ):
        code = "transparent_background_requires_png_or_webp"
        safe_message = "Transparent backgrounds require PNG, WebP or SVG output."
    elif message.startswith("parameter_not_supported_by_binding:"):
        code = "parameter_not_supported_by_binding"
        unsupported = message.split(":", 1)[1].strip()
        safe_message = f"The selected binding does not support: {unsupported}."
    elif message.startswith("custom_size_") and message.endswith(": canvas.size"):
        code = message.split(":", 1)[0]
        safe_message = _CUSTOM_SIZE_MESSAGES.get(code, "The custom size is not allowed for this model.")
    elif message == "image_feature_requires_openai_images":
        code = message
        safe_message = "This model or feature requires an OpenAI Images binding."
    elif message.startswith(("Unknown parameter:", "Parameter is not applicable:")):
        code = "parameter_invalid"
        safe_message = message + "."
    elif "does not support model" in message:
        code = "provider_model_binding_missing"
        safe_message = "The selected provider does not support this model."
    elif "does not support operation" in message:
        code = "operation_unsupported"
        safe_message = "The selected provider does not support this operation."
    elif "Unknown provider" in message:
        code = "provider_not_found"
        safe_message = "The selected provider is not configured."
    elif "Unknown image model" in message:
        code = "model_not_found"
        safe_message = "The selected image model is not available."
    else:
        code = "generation_request_invalid"
        safe_message = "The generation request is invalid."
    return HTTPException(status_code=400, detail={"code": code, "message": safe_message})


def _submission_routing(
    ctx: WebUIContext,
    *,
    operation: str,
    form_fields: frozenset[str],
    canonical_model_id: str | None,
    provider_id: str | None,
    binding_id: str | None,
    parameters_json: str | None,
) -> SubmissionRouting:
    h = ctx.route_helpers
    removed = sorted(form_fields & REMOVED_FORM_FIELDS)
    if removed:
        raise HTTPException(status_code=400, detail={
            "code": "legacy_form_fields_removed",
            "message": LEGACY_FORM_FIELDS_REMOVED_MESSAGE.format(fields=", ".join(removed)),
        })
    # Omitted fields fall back to the default model, the configured source, that
    # provider's default binding and the model's default parameters.
    try:
        parameters = parse_parameters_json(parameters_json)
    except ValueError as exc:
        raise _generation_request_error(exc) from exc
    model_id = str(canonical_model_id or DEFAULT_CANONICAL_MODEL_ID).strip()
    auth_source = _request_auth_source(ctx, provider_id)
    if auth_source == "codex" and not h["codex_auth_checker"]():
        raise HTTPException(status_code=401, detail="Codex auth is not available")
    api_provider_id = h["request_api_provider_id"](auth_source, str(provider_id or "").strip() or None)
    resolved_provider_id = api_provider_id if auth_source == "api" else "codex"
    try:
        binding = resolve_submission_binding(
            operation=operation,  # type: ignore[arg-type]
            canonical_model_id=model_id,
            provider_id=str(resolved_provider_id),
            binding_id=str(binding_id or "").strip() or None,
            codex_mode=str(h["request_codex_mode"]("codex", None)),
            provider_connections=ctx.api_settings.read_connections(),
        )
        model = get_model_manifest(model_id)
    except (KeyError, ValueError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else f"Unknown image model: {model_id}"
        raise _generation_request_error(ValueError(message)) from exc
    responses = binding.protocol_profile in RESPONSES_PROTOCOLS
    capabilities = binding_capabilities(model, binding.protocol_profile, binding.parameter_codec)
    if auth_source == "api":
        requested_backend = BACKEND_OPENAI_RESPONSES if responses else BACKEND_OPENAI_IMAGES
    else:
        requested_backend = BACKEND_CODEX_RESPONSES if responses else BACKEND_CODEX_IMAGES
    return SubmissionRouting(
        auth_source=auth_source,
        canonical_model_id=model_id,
        provider_id=str(resolved_provider_id),
        binding_id=binding.id,
        parameters=parameters,
        requested_backend=requested_backend,
        api_mode=("responses" if responses else "images") if auth_source == "api" else None,
        codex_mode=("responses" if responses else "images") if auth_source == "codex" else None,
        api_provider_id=api_provider_id,
        api_provider_name=h["request_api_provider_name"](auth_source, api_provider_id),
        api_images_concurrency=h["request_api_images_concurrency"](auth_source, api_provider_id),
        uses_main_model=capabilities.uses_main_model,
    )


def _preview_form_generation(
    ctx: WebUIContext,
    *,
    operation: str,
    routing: SubmissionRouting,
    model_prompt: str,
    main_model: str,
    instructions: str | None,
    image_data_urls: list[str],
    mask_data_url: str | None,
    markup_data_url: str | None = None,
    reference_file_inputs: list[ResponsesInputFile],
):
    try:
        command = generation_command_from_form(
            operation=operation,  # type: ignore[arg-type]
            canonical_model_id=routing.canonical_model_id,
            provider_id=routing.provider_id,
            binding_id=routing.binding_id,
            parameters=routing.parameters,
            prompt=model_prompt,
            image_inputs=tuple(ImageInput(item) for item in image_data_urls),
            reference_files=tuple(reference_file_inputs),
            mask_image=mask_data_url,
            markup_image=markup_data_url,
            main_model=main_model,
            instructions=instructions,
        )
        return preview_generation_command(
            command,
            codex_mode=str(routing.codex_mode or "images"),
            provider_connections=ctx.api_settings.read_connections(),
        )
    except ValueError as exc:
        raise _generation_request_error(exc) from exc


def _enqueue_generation(
    ctx: WebUIContext,
    *,
    task_id: str,
    metadata: dict[str, Any],
    plan: Any,
    auth_source: str,
) -> None:
    metadata["generation_snapshot"] = generation_snapshot(plan)
    ctx.storage.write_metadata(task_id, metadata)
    ctx.queue_storage.enqueue(task_id)
    if ctx.queue_manager is not None:
        channels = ctx.route_helpers["queue_channels_for_source"](auth_source)
        ctx.queue_manager.channels = channels
        ctx.queue_manager.max_attempts = ctx.route_helpers["queue_max_attempts_for_channels"](channels)
    ctx.route_helpers["wake_queue_worker"]()


def _prepare_generation_submission(
    ctx: WebUIContext,
    *,
    operation: str,
    routing: SubmissionRouting,
    prompt: str,
    prompt_for_model: str | None,
    ui_language: str,
    main_model: str,
    image_data_urls: list[str],
    mask_data_url: str | None,
    markup_data_url: str | None = None,
    reference_file_inputs: list[ResponsesInputFile],
    resolved_original_prompt: str | None = None,
) -> PreparedGenerationSubmission:
    h = ctx.route_helpers
    effective_main_model = main_model if routing.uses_main_model else ""
    # Prompt processing is disabled: no ratio or guard instructions are added.
    # The model still gets expanded snippets and gallery reference notes, either
    # from the WebUI composer or by expanding snippets for direct API callers.
    # The routes default a missing prompt_for_model to the prompt itself, so an
    # unchanged prompt means no composed version was sent.
    original_prompt = resolved_original_prompt if resolved_original_prompt is not None else prompt
    composed_prompt = str(prompt_for_model or "")
    if not composed_prompt or composed_prompt in {prompt, original_prompt}:
        composed_prompt = h["model_prompt_for_fidelity"](original_prompt, None, "original")
    model_prompt = str(composed_prompt or "")
    plan = _preview_form_generation(
        ctx,
        operation=operation,
        routing=routing,
        model_prompt=model_prompt,
        main_model=effective_main_model,
        instructions=None,
        image_data_urls=image_data_urls,
        mask_data_url=mask_data_url,
        markup_data_url=markup_data_url,
        reference_file_inputs=reference_file_inputs,
    )
    protocol_preview = redacted_protocol_request(plan)
    request_payload = dict(protocol_preview.json_body or protocol_preview.form_fields)
    params = task_params_from_plan(plan, main_model=effective_main_model)
    if routing.codex_mode is not None:
        params["codex_mode"] = routing.codex_mode
    if routing.api_mode is not None:
        params["api_mode"] = routing.api_mode
    if routing.api_provider_id is not None:
        params["api_provider_id"] = routing.api_provider_id
    if routing.api_provider_name:
        params["api_provider_name"] = routing.api_provider_name
    if routing.auth_source == "api":
        params["api_images_concurrency"] = routing.api_images_concurrency
    return PreparedGenerationSubmission(
        plan=plan,
        request_payload=request_payload,
        model_prompt=model_prompt,
        prompt_constraints=[],
        params=params,
        prompt_locale=str(ui_language or "zh-CN"),
    )


def _persist_generation_submission(
    ctx: WebUIContext,
    *,
    prepared: PreparedGenerationSubmission,
    operation: str,
    task_id: str,
    created_at: str,
    prompt: str,
    requested_backend: str,
    auth_source: str,
    effective_api_provider_id: str | None,
    effective_api_provider_name: str | None,
    effective_api_images_concurrency: int,
    input_files: list[Path],
    mask_file: str | None,
    markup_file: str | None = None,
    gallery_refs: list[dict[str, Any]],
    reference_assets: list[dict[str, Any]],
    file_references: list[dict[str, Any]],
    reference_image_order: list[dict[str, str]] | None,
    prompt_image_mentions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    h = ctx.route_helpers
    stored_request_payload = h["slim_request_payload"](
        prepared.request_payload,
        input_files=[path.name for path in input_files],
        gallery_refs=gallery_refs,
        reference_assets=reference_assets,
        reference_files=file_references,
        mask_file=mask_file,
        markup_file=markup_file,
    )
    if reference_image_order is not None:
        stored_request_payload["webui_image_refs"]["reference_image_order"] = reference_image_order
    stored_request_payload["webui_requested_backend"] = requested_backend
    if effective_api_provider_id is not None:
        stored_request_payload["webui_api_provider_id"] = effective_api_provider_id
    if effective_api_provider_name:
        stored_request_payload["webui_api_provider_name"] = effective_api_provider_name
    if auth_source == "api":
        stored_request_payload["webui_api_images_concurrency"] = (
            effective_api_images_concurrency
        )
    ctx.storage.write_request(task_id, stored_request_payload)

    metadata = _write_queued_metadata(
        ctx.storage,
        task_id,
        created_at=created_at,
        mode=operation,
        prompt=prompt,
        prompt_for_model=prepared.model_prompt,
        execution_model_prompt=prepared.model_prompt,
        execution_prompt=str(prepared.plan.command.prompt),
        execution_instructions=prepared.plan.command.instructions,
        prompt_locale=prepared.prompt_locale,
        params=prepared.params,
        input_files=[path.name for path in input_files],
        mask_file=mask_file,
        markup_file=markup_file,
        gallery_refs=gallery_refs,
        reference_assets=reference_assets,
        reference_files=file_references,
        reference_image_order=reference_image_order,
        prompt_image_mentions=prompt_image_mentions,
        prompt_constraints=prepared.prompt_constraints,
        requested_backend=requested_backend,
        max_attempts=ctx.queue_manager.max_attempts if ctx.queue_manager is not None else 1,
    )
    _enqueue_generation(
        ctx,
        task_id=task_id,
        metadata=metadata,
        plan=prepared.plan,
        auth_source=auth_source,
    )
    return {
        "task": _with_file_urls(
            metadata,
            ctx.active_task_ids,
            ctx.gallery_storage,
            ctx.reference_asset_storage,
            ctx.reference_file_storage,
        ),
        "request": stored_request_payload,
    }


def _reject_cached_unsupported_reference_files(
    ctx: WebUIContext,
    *,
    has_reference_files: bool,
    requested_backend: str,
    provider_id: str | None,
    main_model: str,
) -> None:
    if not has_reference_files:
        return
    key = reference_file_capability_key_for_backend(
        requested_backend=requested_backend,
        provider_id=str(provider_id or ""),
        main_model=main_model,
        api_settings=ctx.api_settings,
    )
    if key in ctx.responses_file_unsupported_keys:
        raise HTTPException(status_code=400, detail=PROVIDER_REFERENCE_FILES_UNSUPPORTED_DETAIL)


@contextmanager
def _retain_selected_reference_assets(ctx: WebUIContext, asset_ids: list[str]) -> Iterator[None]:
    with ExitStack() as stack:
        try:
            stack.enter_context(ctx.reference_asset_storage.retain_for_submission(_dedupe_preserve_order(asset_ids)))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid reference asset id") from exc
        yield


async def _prepare_reference_files(
    storage: ReferenceFileStorage,
    uploads: list[UploadFile],
    asset_ids: list[str],
) -> PreparedReferenceFiles:
    try:
        validated_uploads = await read_reference_file_uploads(uploads)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=400,
            detail={"code": code, "message": REFERENCE_FILE_ERROR_MESSAGES.get(code, "The reference file is invalid.")},
        ) from exc
    try:
        selected_records = resolve_reference_file_ids(storage, asset_ids, touch=False)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=REFERENCE_FILE_MISSING_DETAIL) from exc
    verified_selected_records, selected_inputs = _resolve_reference_files(
        storage,
        selected_records,
    )

    predicted_records = dedupe_reference_file_records(
        [reference_file_task_record(upload) for upload in validated_uploads]
        + verified_selected_records
    )
    try:
        validate_reference_file_total(predicted_records)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=400,
            detail={"code": code, "message": REFERENCE_FILE_ERROR_MESSAGES.get(code, "The reference file is invalid.")},
        ) from exc

    uploads_by_id = {
        upload.asset_id: upload
        for upload in validated_uploads
    }
    selected_inputs_by_id = {
        str(record["id"]): response_input
        for record, response_input in zip(
            verified_selected_records,
            selected_inputs,
            strict=True,
        )
    }
    response_inputs: list[ResponsesInputFile] = []
    for record in predicted_records:
        asset_id = str(record["id"])
        upload = uploads_by_id.get(asset_id)
        if upload is not None:
            response_inputs.append(
                _reference_file_to_responses_input(
                    Path(upload.filename),
                    record,
                    data=upload.data,
                )
            )
        else:
            response_inputs.append(selected_inputs_by_id[asset_id])
    return PreparedReferenceFiles(
        uploads=tuple(validated_uploads),
        selected_asset_ids=tuple(
            dict.fromkeys(str(value or "").strip() for value in asset_ids)
        ),
        records=tuple(predicted_records),
        response_inputs=tuple(response_inputs),
    )


def _commit_reference_files(
    storage: ReferenceFileStorage,
    prepared: PreparedReferenceFiles,
) -> list[dict[str, Any]]:
    try:
        return storage.commit_batch(
            prepared.uploads,
            prepared.selected_asset_ids,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "reference_file_missing":
            raise HTTPException(status_code=404, detail=REFERENCE_FILE_MISSING_DETAIL) from exc
        stable_code = code if code in REFERENCE_FILE_ERROR_MESSAGES else "reference_file_invalid"
        raise HTTPException(
            status_code=400,
            detail={
                "code": stable_code,
                "message": REFERENCE_FILE_ERROR_MESSAGES[stable_code],
            },
        ) from exc


async def _prepare_raster_uploads(
    uploads: list[UploadFile],
    *, preserve_positions: bool = False,
) -> list[ValidatedRasterImage]:
    try:
        return await read_validated_raster_uploads(uploads, deduplicate=not preserve_positions)
    except InvalidRasterImage as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _prepared_reference_asset(image: ValidatedRasterImage) -> dict[str, Any]:
    return {
        "id": image.sha256,
        "sha256": image.sha256,
        "filename": image.filename,
        "mime_type": image.mime_type,
        "size_bytes": len(image.data),
    }


def _commit_reference_assets(
    ctx: WebUIContext,
    *,
    uploads: list[ValidatedRasterImage],
    predicted_assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    uploads_by_id = {image.sha256: image for image in uploads}
    committed: list[dict[str, Any]] = []
    for predicted in predicted_assets:
        asset_id = str(predicted.get("id") or "")
        upload = uploads_by_id.get(asset_id)
        try:
            if upload is not None:
                item = ctx.reference_asset_storage.create_or_touch(
                    upload.filename,
                    upload.data,
                    upload.mime_type,
                )
            else:
                item = ctx.reference_asset_storage.touch(asset_id)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=404,
                detail=f"Reference asset not found: {asset_id}",
            ) from exc
        committed.append(item)
    return committed


def _predicted_reference_data_urls(
    ctx: WebUIContext,
    *,
    uploads: list[ValidatedRasterImage],
    predicted_assets: list[dict[str, Any]],
) -> list[str]:
    uploads_by_id = {image.sha256: image for image in uploads}
    data_urls: list[str] = []
    for item in predicted_assets:
        asset_id = str(item["id"])
        upload = uploads_by_id.get(asset_id)
        if upload is not None:
            data_urls.append(
                _bytes_to_data_url(
                    upload.data,
                    filename=upload.filename,
                    mime_type=upload.mime_type,
                )
            )
        else:
            data_urls.append(
                _file_to_data_url(
                    ctx.reference_asset_storage.image_path(asset_id),
                    mime_type=str(item.get("mime_type") or ""),
                )
            )
    return data_urls


def _validate_task_image_resources(
    *,
    reference_assets: list[dict[str, Any]],
    gallery_refs: list[dict[str, Any]],
    mask: ValidatedRasterImage | None = None,
    markup: ValidatedRasterImage | None = None,
) -> None:
    resources: list[TaskImageResource] = []
    for item in [*reference_assets, *gallery_refs]:
        digest = str(item.get("sha256") or item.get("id") or "").strip()
        resources.append(
            TaskImageResource(
                key=f"content:{digest}",
                size_bytes=int(item.get("size_bytes") or 0),
            )
        )
    if mask is not None:
        resources.append(
            TaskImageResource(
                key=f"content:{mask.sha256}",
                size_bytes=len(mask.data),
            )
        )
    if markup is not None:
        resources.append(TaskImageResource(key=f"content:{markup.sha256}", size_bytes=len(markup.data)))
    try:
        validate_task_image_total(
            resources,
            max_total_bytes=MAX_TASK_IMAGE_BYTES,
        )
    except TaskImageLimitError as exc:
        raise HTTPException(
            status_code=413,
            detail=TASK_IMAGES_TOTAL_TOO_LARGE_DETAIL,
        ) from exc


def _gallery_data_urls(
    ctx: WebUIContext,
    gallery_refs: list[dict[str, Any]],
) -> list[str]:
    return [
        _file_to_data_url(
            ctx.gallery_storage.image_path(str(item["id"])),
            mime_type="",
        )
        for item in gallery_refs
    ]


def register_generation_routes(app: FastAPI, ctx: WebUIContext) -> None:
    h = ctx.route_helpers

    @app.post("/api/generate")
    async def generate(
        request: Request,
        prompt: str = Form(...),
        ui_language: str = Form("zh-CN"),
        main_model: str = Form(DEFAULT_MAIN_MODEL),
        canonical_model_id: str | None = Form(None),
        provider_id: str | None = Form(None),
        binding_id: str | None = Form(None),
        parameters_json: str | None = Form(None),
        prompt_for_model: str | None = Form(None),
        gallery_prompt: str | None = Form(None),
        prompt_image_mentions: str | None = Form(None),
        gallery_image_ids: list[str] | None = Form(None),
        reference_asset_ids: list[str] | None = Form(None),
        reference_image_order: str | None = Form(None),
        reference_file_ids: list[str] | None = Form(None),
        reference_images: list[UploadFile] | None = File(None),
        reference_files: list[UploadFile] | None = File(None),
    ) -> dict[str, Any]:
        routing = _submission_routing(
            ctx,
            operation="generate",
            form_fields=frozenset(str(key) for key in (await request.form()).keys()),
            canonical_model_id=canonical_model_id,
            provider_id=provider_id,
            binding_id=binding_id,
            parameters_json=parameters_json,
        )
        main_model = effective_reference_file_main_model(main_model)
        auth_source = routing.auth_source
        requested_backend = routing.requested_backend
        effective_api_provider_id = routing.api_provider_id
        effective_api_provider_name = routing.api_provider_name
        effective_api_images_concurrency = routing.api_images_concurrency
        if (reference_files or reference_file_ids) and not requested_backend.endswith("_responses"):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "reference_files_require_responses",
                    "message": "Reference files require a Responses backend.",
                },
            )
        _reject_cached_unsupported_reference_files(
            ctx,
            has_reference_files=bool(reference_files or reference_file_ids),
            requested_backend=requested_backend,
            provider_id=effective_api_provider_id,
            main_model=main_model,
        )

        gallery_refs, _ = _resolve_gallery_refs(
            ctx.gallery_storage,
            gallery_image_ids or [],
            include_data_urls=False,
        )
        with _retain_selected_reference_assets(ctx, reference_asset_ids or []):
            uploaded_images = await _prepare_raster_uploads(reference_images or [], preserve_positions=reference_image_order is not None)
            predicted_uploaded_assets = [
                _prepared_reference_asset(image)
                for image in uploaded_images
            ]
            selected_assets, _ = _resolve_reference_assets(
                ctx.reference_asset_storage,
                reference_asset_ids or [],
                touch=False,
                include_data_urls=False,
            )
            image_order = normalize_reference_image_order(
                reference_image_order, predicted_uploaded_assets, selected_assets, gallery_refs,
            )
            resolved_original, prompt_for_model, resolved_mentions = resolve_prompt_image_mentions(
                prompt_image_mentions, prompt, prompt_for_model or prompt, predicted_uploaded_assets, image_order,
            )
            prompt_for_model = resolve_gallery_prompt(prompt_for_model, gallery_prompt, image_order)
            predicted_assets = h["dedupe_reference_assets"](
                predicted_uploaded_assets + selected_assets
            )
            _validate_task_image_resources(
                reference_assets=predicted_assets,
                gallery_refs=gallery_refs,
            )
            prepared_reference_files = await _prepare_reference_files(
                ctx.reference_file_storage,
                reference_files or [],
                reference_file_ids or [],
            )
            reference_data_urls = _predicted_reference_data_urls(
                ctx,
                uploads=uploaded_images,
                predicted_assets=predicted_assets,
            )
            gallery_data_urls = _gallery_data_urls(ctx, gallery_refs)
            all_reference_data_urls = ordered_reference_data_urls(
                predicted_assets, reference_data_urls, gallery_refs, gallery_data_urls, image_order,
            )
            prepared_submission = _prepare_generation_submission(
                ctx,
                operation="generate",
                routing=routing,
                prompt=prompt,
                prompt_for_model=prompt_for_model,
                ui_language=ui_language,
                main_model=main_model,
                image_data_urls=all_reference_data_urls,
                mask_data_url=None,
                reference_file_inputs=list(prepared_reference_files.response_inputs),
                resolved_original_prompt=resolved_original if resolved_mentions is not None else None,
            )

            with ctx.reference_asset_storage.protect_submission(item["id"] for item in predicted_assets):
                reference_assets = _commit_reference_assets(
                    ctx,
                    uploads=uploaded_images,
                    predicted_assets=predicted_assets,
                )
                file_references = _commit_reference_files(
                    ctx.reference_file_storage,
                    prepared_reference_files,
                )
                task = ctx.storage.create_task("generate")
                return _persist_generation_submission(
                    ctx,
                    prepared=prepared_submission,
                    operation="generate",
                    task_id=task.task_id,
                    created_at=utc_now(),
                    prompt=prompt,
                    requested_backend=requested_backend,
                    auth_source=auth_source,
                    effective_api_provider_id=effective_api_provider_id,
                    effective_api_provider_name=effective_api_provider_name,
                    effective_api_images_concurrency=effective_api_images_concurrency,
                    input_files=[],
                    mask_file=None,
                    gallery_refs=gallery_refs,
                    reference_assets=reference_assets,
                    file_references=file_references,
                    reference_image_order=image_order,
                    prompt_image_mentions=resolved_mentions,
                )

    @app.post("/api/edit")
    async def edit(
        request: Request,
        prompt: str = Form(...),
        ui_language: str = Form("zh-CN"),
        main_model: str = Form(DEFAULT_MAIN_MODEL),
        canonical_model_id: str | None = Form(None),
        provider_id: str | None = Form(None),
        binding_id: str | None = Form(None),
        parameters_json: str | None = Form(None),
        prompt_for_model: str | None = Form(None),
        gallery_prompt: str | None = Form(None),
        prompt_image_mentions: str | None = Form(None),
        gallery_image_ids: list[str] | None = Form(None),
        reference_asset_ids: list[str] | None = Form(None),
        reference_image_order: str | None = Form(None),
        reference_file_ids: list[str] | None = Form(None),
        images: list[UploadFile] | None = File(None),
        mask: UploadFile | None = File(None),
        markup: UploadFile | None = File(None),
        reference_files: list[UploadFile] | None = File(None),
    ) -> dict[str, Any]:
        routing = _submission_routing(
            ctx,
            operation="edit",
            form_fields=frozenset(str(key) for key in (await request.form()).keys()),
            canonical_model_id=canonical_model_id,
            provider_id=provider_id,
            binding_id=binding_id,
            parameters_json=parameters_json,
        )
        main_model = effective_reference_file_main_model(main_model)
        auth_source = routing.auth_source
        requested_backend = routing.requested_backend
        effective_api_provider_id = routing.api_provider_id
        effective_api_provider_name = routing.api_provider_name
        effective_api_images_concurrency = routing.api_images_concurrency
        if (reference_files or reference_file_ids) and not requested_backend.endswith("_responses"):
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "reference_files_require_responses",
                    "message": "Reference files require a Responses backend.",
                },
            )
        _reject_cached_unsupported_reference_files(
            ctx,
            has_reference_files=bool(reference_files or reference_file_ids),
            requested_backend=requested_backend,
            provider_id=effective_api_provider_id,
            main_model=main_model,
        )

        gallery_refs, _ = _resolve_gallery_refs(
            ctx.gallery_storage,
            gallery_image_ids or [],
            include_data_urls=False,
        )
        with _retain_selected_reference_assets(ctx, reference_asset_ids or []):
            uploaded_images = await _prepare_raster_uploads(images or [], preserve_positions=reference_image_order is not None)
            prepared_masks = await _prepare_raster_uploads(
                [mask] if mask is not None else []
            )
            prepared_mask = prepared_masks[0] if prepared_masks else None
            prepared_markups = await _prepare_raster_uploads([markup] if markup is not None else [])
            prepared_markup = prepared_markups[0] if prepared_markups else None
            markup_data_url = (
                _bytes_to_data_url(prepared_markup.data, filename=prepared_markup.filename,
                                   mime_type=prepared_markup.mime_type)
                if prepared_markup is not None else None
            )
            predicted_uploaded_assets = [
                _prepared_reference_asset(image)
                for image in uploaded_images
            ]
            selected_assets, _ = _resolve_reference_assets(
                ctx.reference_asset_storage,
                reference_asset_ids or [],
                touch=False,
                include_data_urls=False,
            )
            image_order = normalize_reference_image_order(
                reference_image_order, predicted_uploaded_assets, selected_assets, gallery_refs,
            )
            resolved_original, prompt_for_model, resolved_mentions = resolve_prompt_image_mentions(
                prompt_image_mentions, prompt, prompt_for_model or prompt, predicted_uploaded_assets, image_order,
            )
            prompt_for_model = resolve_gallery_prompt(prompt_for_model, gallery_prompt, image_order)
            predicted_assets = h["dedupe_reference_assets"](
                predicted_uploaded_assets + selected_assets
            )
            if not predicted_assets and not gallery_refs:
                raise HTTPException(status_code=400, detail="At least one image is required")
            _validate_task_image_resources(
                reference_assets=predicted_assets,
                gallery_refs=gallery_refs,
                mask=prepared_mask,
                markup=prepared_markup,
            )
            prepared_reference_files = await _prepare_reference_files(
                ctx.reference_file_storage,
                reference_files or [],
                reference_file_ids or [],
            )
            image_data_urls = _predicted_reference_data_urls(
                ctx,
                uploads=uploaded_images,
                predicted_assets=predicted_assets,
            )
            gallery_data_urls = _gallery_data_urls(ctx, gallery_refs)
            all_image_data_urls = ordered_reference_data_urls(
                predicted_assets, image_data_urls, gallery_refs, gallery_data_urls, image_order,
            )
            mask_data_url = (
                _bytes_to_data_url(
                    prepared_mask.data,
                    filename=prepared_mask.filename,
                    mime_type=prepared_mask.mime_type,
                )
                if prepared_mask is not None
                else None
            )
            prepared_submission = _prepare_generation_submission(
                ctx,
                operation="edit",
                routing=routing,
                prompt=prompt,
                prompt_for_model=prompt_for_model,
                ui_language=ui_language,
                main_model=main_model,
                image_data_urls=all_image_data_urls,
                mask_data_url=mask_data_url,
                markup_data_url=markup_data_url,
                reference_file_inputs=list(prepared_reference_files.response_inputs),
                resolved_original_prompt=resolved_original if resolved_mentions is not None else None,
            )

            with ctx.reference_asset_storage.protect_submission(item["id"] for item in predicted_assets):
                reference_assets = _commit_reference_assets(
                    ctx,
                    uploads=uploaded_images,
                    predicted_assets=predicted_assets,
                )
                file_references = _commit_reference_files(
                    ctx.reference_file_storage,
                    prepared_reference_files,
                )
                task = ctx.storage.create_task("edit")
                mask_files = (
                    [
                        ctx.storage.write_input(
                            task.task_id,
                            prepared_mask.filename,
                            prepared_mask.data,
                            kind="mask",
                            index=1,
                        )
                    ]
                    if prepared_mask is not None
                    else []
                )
                mask_file = mask_files[0].name if mask_files else None
                markup_file = (
                    ctx.storage.write_input(task.task_id, "markup.png", prepared_markup.data,
                                            kind="markup", index=1).name
                    if prepared_markup is not None else None
                )
                return _persist_generation_submission(
                    ctx,
                    prepared=prepared_submission,
                    operation="edit",
                    task_id=task.task_id,
                    created_at=utc_now(),
                    prompt=prompt,
                    requested_backend=requested_backend,
                    auth_source=auth_source,
                    effective_api_provider_id=effective_api_provider_id,
                    effective_api_provider_name=effective_api_provider_name,
                    effective_api_images_concurrency=effective_api_images_concurrency,
                    input_files=[],
                    mask_file=mask_file,
                    markup_file=markup_file,
                    gallery_refs=gallery_refs,
                    reference_assets=reference_assets,
                    file_references=file_references,
                    reference_image_order=image_order,
                    prompt_image_mentions=resolved_mentions,
                )
