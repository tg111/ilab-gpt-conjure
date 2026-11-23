"""Golden API requests for every model, protocol and representative parameter set.

The unified generation form changes how parameters are named and validated, but
the requests sent to providers must stay byte-for-byte the same. This suite
records the request each case produces (or the error it raises) and compares it
with ``tests/fixtures/request_snapshots.json``.

Regenerate the fixture only for an intended request change:
    UPDATE_REQUEST_SNAPSHOTS=1 .venv/bin/python -m unittest tests.test_request_snapshots
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import unittest
from pathlib import Path
from typing import Any

from PIL import Image

from codex_image.generation.types import GenerationCommand, ImageInput
from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
from codex_image.webui.generation_request import preview_generation_command

FIXTURE = Path(__file__).parent / "fixtures" / "request_snapshots.json"
PROMPT = "a small red fox in the snow"


def _png_data_url(size: tuple[int, int] = (64, 48)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, (90, 140, 120)).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


IMAGE = ImageInput(_png_data_url())

GPT_MODELS = ("gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.6-sunburst")
GEMINI_MODELS = ("nano-banana-pro", "nano-banana-2.1", "nano-banana-2", "nano-banana-2-lite")
GPT_PROTOCOLS = (
    ("openai_images", "gpt_openai_images"),
    ("openai_responses", "gpt_openai_responses"),
    ("codex_images", "gpt_codex_images"),
    ("codex_responses", "gpt_codex_responses"),
)
GEMINI_PROTOCOLS = (
    ("gemini_generate_content", "gemini_generate_content_image"),
    ("gemini_generate_content", "gemini_generate_content_image_config"),
    ("gemini_change2pro_generate_content", "gemini_generate_content_image_config"),
    ("gemini_interactions", "gemini_interactions_image"),
    ("openai_images", "gemini_openai_images"),
    ("t8_images", "gemini_t8_images"),
    ("openrouter_images", "gemini_openrouter_images"),
)

# Parameter sets in the vocabulary the current WebUI submits.
GPT_PARAMETER_SETS: dict[str, dict[str, Any]] = {
    "preset": {"canvas.size": "1536x1024", "gpt.quality": "high", "gpt.background": "auto",
               "output.format": "png", "gpt.moderation": "low", "output.count": 2},
    "auto-size": {"canvas.size": "auto", "gpt.quality": "auto", "output.format": "png", "output.count": 1},
    "custom-size": {"canvas.size": "1600x896", "gpt.quality": "medium", "output.format": "png"},
    "jpeg-compression": {"canvas.size": "1024x1024", "output.format": "jpeg", "gpt.output_compression": 70},
    "transparent": {"canvas.size": "1024x1024", "gpt.background": "transparent", "output.format": "png"},
    "web-search": {"canvas.size": "1024x1024", "gpt.web_search": True},
    "web-search-off": {"canvas.size": "1024x1024", "gpt.web_search": False},
}
GPT_26_PARAMETER_SETS: dict[str, dict[str, Any]] = {
    "complexity": {"canvas.size": "1024x1024", "gpt.quality": "max", "gpt.complexity": "medium"},
    "gif": {"canvas.size": "1024x1024", "output.format": "gif", "gpt.frame_count": 6, "gpt.frame_duration_ms": 120},
    "svg": {"canvas.size": "1024x1024", "output.format": "svg", "output.count": 2},
}
GEMINI_PARAMETER_SETS: dict[str, dict[str, Any]] = {
    "defaults": {},
    "wide-2k": {"canvas.aspect_ratio": "16:9", "canvas.resolution": "2K", "output.count": 2},
    "search": {"canvas.aspect_ratio": "1:1", "canvas.resolution": "1K", "gemini.google_search": True},
    "safety": {"gemini.safety_settings": {"HARM_CATEGORY_HARASSMENT": "BLOCK_ONLY_HIGH"}},
}


# The same choices in the unified vocabulary; each must produce the identical request.
UNIFIED_GPT_PARAMETER_SETS: dict[str, dict[str, Any]] = {
    "preset": {"canvas.mode": "preset", "canvas.aspect_ratio": "3:2", "canvas.resolution": "1K",
               "gpt.quality": "high", "gpt.background": "auto", "output.format": "png",
               "gpt.moderation": "low", "output.count": 2},
    "auto-size": {"canvas.mode": "auto", "gpt.quality": "auto", "output.format": "png", "output.count": 1},
    "custom-size": {"canvas.mode": "custom", "canvas.size": "1600x896", "gpt.quality": "medium", "output.format": "png"},
    "jpeg-compression": {"canvas.mode": "preset", "canvas.aspect_ratio": "1:1", "canvas.resolution": "1K",
                         "output.format": "jpeg", "gpt.output_compression": 70},
    "transparent": {"canvas.mode": "preset", "canvas.aspect_ratio": "1:1", "canvas.resolution": "1K",
                    "gpt.background": "transparent", "output.format": "png"},
    "web-search": {"canvas.mode": "preset", "tools.web_search": True},
    "web-search-off": {"canvas.mode": "preset", "tools.web_search": False},
}
UNIFIED_GPT_26_PARAMETER_SETS: dict[str, dict[str, Any]] = {
    "complexity": {"canvas.mode": "preset", "gpt.quality": "max", "gpt.complexity": "medium"},
    "gif": {"canvas.mode": "preset", "output.format": "gif", "gpt.frame_count": 6, "gpt.frame_duration_ms": 120},
    "svg": {"canvas.mode": "preset", "output.format": "svg", "output.count": 2},
}
UNIFIED_GEMINI_PARAMETER_SETS: dict[str, dict[str, Any]] = {
    "defaults": {},
    "wide-2k": {"canvas.mode": "preset", "canvas.aspect_ratio": "16:9", "canvas.resolution": "2K", "output.count": 2},
    "search": {"canvas.mode": "preset", "canvas.aspect_ratio": "1:1", "canvas.resolution": "1K", "tools.web_search": True},
    "safety": {"gemini.safety_settings": {"HARM_CATEGORY_HARASSMENT": "BLOCK_ONLY_HIGH"}},
}


def _unified_parameters(model: str, name: str) -> dict[str, Any]:
    if model.startswith("gpt-image-"):
        return {**UNIFIED_GPT_PARAMETER_SETS, **UNIFIED_GPT_26_PARAMETER_SETS}[name]
    return UNIFIED_GEMINI_PARAMETER_SETS[name]


def _cases() -> list[tuple[str, str, str, str, str, dict[str, Any]]]:
    cases = []
    for model in GPT_MODELS:
        sets = dict(GPT_PARAMETER_SETS)
        if model.startswith("gpt-image-2.6-"):
            sets.update(GPT_26_PARAMETER_SETS)
        for protocol, codec in GPT_PROTOCOLS:
            for operation in ("generate", "edit"):
                for name, parameters in sets.items():
                    cases.append((model, protocol, codec, operation, name, parameters))
    for model in GEMINI_MODELS:
        for protocol, codec in GEMINI_PROTOCOLS:
            for operation in ("generate", "edit"):
                for name, parameters in GEMINI_PARAMETER_SETS.items():
                    cases.append((model, protocol, codec, operation, name, parameters))
    return cases


def _request_record(model: str, protocol: str, codec: str, operation: str, parameters: dict[str, Any]) -> dict[str, Any]:
    binding = ProviderModelBinding(
        "b", "relay", model, f"vendor/{model}", protocol, codec, frozenset({"generate", "edit"}),
    )
    provider = ProviderConnection("relay", "Relay", "https://relay.example/v1", "test-key", 1, (binding,))
    command = GenerationCommand(
        operation, model, "relay", PROMPT, dict(parameters),
        image_inputs=(IMAGE,) if operation == "edit" else (),
        main_model="gpt-6-luna" if protocol.endswith("responses") else None,
    )
    try:
        plan = preview_generation_command(command, codex_mode="images", provider_connections=[provider])
    except ValueError as exc:
        return {"error": str(exc)}
    request = plan.protocol_request
    return {
        "method": request.method,
        "path": request.path,
        "content_type": request.content_type,
        "json_body": request.json_body,
        "form_fields": [list(item) for item in request.form_fields] if isinstance(request.form_fields, (list, tuple)) else request.form_fields,
        "files": [
            {"field": field, "filename": filename, "mime_type": mime_type,
             "sha256": hashlib.sha256(data if isinstance(data, bytes) else str(data).encode()).hexdigest()}
            for field, filename, mime_type, data in request.files
        ],
        "repeat_count": request.repeat_count,
    }


def _current_records() -> dict[str, Any]:
    records = {}
    for model, protocol, codec, operation, name, parameters in _cases():
        key = f"{model} | {protocol}/{codec} | {operation} | {name}"
        records[key] = _request_record(model, protocol, codec, operation, parameters)
    return records


class RequestSnapshotTests(unittest.TestCase):
    def test_requests_match_recorded_snapshots(self) -> None:
        current = json.loads(json.dumps(_current_records(), sort_keys=True, default=str))
        if os.environ.get("UPDATE_REQUEST_SNAPSHOTS") == "1":
            FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            FIXTURE.write_text(json.dumps(current, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(sorted(current), sorted(recorded), "case list changed")
        for key in recorded:
            with self.subTest(case=key):
                self.assertEqual(current[key], recorded[key])

    def test_unified_vocabulary_sends_the_same_requests(self) -> None:
        recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for model, protocol, codec, operation, name, _ in _cases():
            key = f"{model} | {protocol}/{codec} | {operation} | {name}"
            expected = recorded[key]
            if "error" in expected:
                continue
            with self.subTest(case=key):
                current = json.loads(json.dumps(
                    _request_record(model, protocol, codec, operation, _unified_parameters(model, name)),
                    sort_keys=True, default=str,
                ))
                self.assertEqual(current, expected)

    def test_snapshot_cover_success_and_error_paths(self) -> None:
        recorded = json.loads(FIXTURE.read_text(encoding="utf-8"))
        successes = [key for key, value in recorded.items() if "error" not in value]
        errors = [key for key, value in recorded.items() if "error" in value]
        self.assertGreater(len(successes), 200)
        self.assertGreater(len(errors), 0)


if __name__ == "__main__":
    unittest.main()
