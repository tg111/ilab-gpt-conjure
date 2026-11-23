"""Submissions route by the selected binding and accept only the unified parameters."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from codex_image.generation.types import GenerationCommand
from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
from codex_image.webui.generation_request import preview_generation_command, task_params_from_plan


def _relay_settings() -> dict:
    """A Responses relay whose stored mode still says Images, and a plain Images relay."""
    def provider(provider_id: str, protocol: str) -> dict:
        return {
            "id": provider_id, "name": provider_id, "base_url": "https://relay.example/v1",
            "api_key": "unit-test-secret", "auth_scheme": "bearer", "concurrency": 2, "api_mode": "images",
            "bindings": [{
                "id": f"{provider_id}-gpt", "canonical_model_id": "gpt-image-2", "remote_model_id": "relay/gpt-image-2",
                "protocol_profile": f"openai_{protocol}", "parameter_codec": f"gpt_openai_{protocol}",
                "operations": ["generate", "edit"],
            }],
        }
    return {
        "schema_version": 2,
        "active_provider_id": "relay",
        "default_provider_by_model": {"gpt-image-2": "relay"},
        "providers": [provider("relay", "responses"), provider("relay-images", "images")],
    }


class SubmissionRoutingTests(unittest.TestCase):
    def _client(self, root: Path) -> TestClient:
        from codex_image.webui.app import create_app

        api_path = root / "api-settings.json"
        api_path.write_text(json.dumps(_relay_settings()), encoding="utf-8")
        return TestClient(create_app(
            output_root=root / "outputs",
            api_settings_path=api_path,
            auth_settings_path=root / "auth-settings.json",
            webui_settings_path=root / "webui-settings.json",
            client_factory=lambda: object(),
            auth_checker=lambda: True,
            auto_start_queue=False,
        ))

    def _submit(self, client: TestClient, provider_id: str, parameters: dict, **extra) -> dict:
        response = client.post("/api/generate", data={
            "prompt": "fox", "canonical_model_id": "gpt-image-2", "provider_id": provider_id,
            "binding_id": f"{provider_id}-gpt", "parameters_json": json.dumps(parameters), **extra,
        })
        return {"status": response.status_code, **response.json()}

    def test_backend_and_main_model_follow_the_selected_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(Path(tmp))
            responses = self._submit(client, "relay", {"tools.web_search": True}, main_model="gpt-5.5")
            images = self._submit(client, "relay-images", {}, main_model="gpt-5.5")

        self.assertEqual(responses["status"], 200, responses)
        # The provider's stored mode says Images; the chosen Responses binding decides.
        self.assertEqual(responses["task"]["requested_backend"], "openai_responses")
        self.assertEqual(responses["task"]["params"]["api_mode"], "responses")
        self.assertEqual(responses["task"]["params"]["main_model"], "gpt-5.5")
        self.assertTrue(responses["task"]["params"]["web_search"])
        self.assertEqual(responses["task"]["generation_snapshot"]["binding_id"], "relay-gpt")
        self.assertEqual(images["task"]["requested_backend"], "openai_images")
        self.assertNotIn("main_model", images["task"]["params"])

    def test_reference_files_are_accepted_on_a_responses_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(Path(tmp))
            response = client.post(
                "/api/generate",
                data={"prompt": "use the brief", "canonical_model_id": "gpt-image-2", "provider_id": "relay",
                      "binding_id": "relay-gpt", "parameters_json": "{}"},
                files={"reference_files": ("brief.pdf", b"%PDF-1.4\nbrief", "application/pdf")},
            )
        self.assertEqual(response.status_code, 200, response.text)

    def test_unsupported_choices_are_refused_with_readable_codes(self) -> None:
        cases = (
            ("relay-images", {"tools.web_search": True}, "parameter_not_supported_by_binding"),
            ("relay-images", {"canvas.mode": "custom", "canvas.size": "1000x1008"}, "custom_size_not_multiple"),
            ("relay-images", {"gpt.background": "transparent", "output.format": "jpeg"},
             "transparent_background_requires_png_or_webp"),
            ("relay-images", {"canvas.mode": "auto", "canvas.aspect_ratio": "1:1"}, "parameter_invalid"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            client = self._client(Path(tmp))
            for binding_id, parameters, code in cases:
                with self.subTest(code=code):
                    result = self._submit(client, binding_id, parameters)
                    self.assertEqual(result["status"], 400)
                    self.assertEqual(result["detail"]["code"], code)
                    self.assertNotEqual(result["detail"]["message"], "The generation request is invalid.")


class TaskParamsTests(unittest.TestCase):
    def _plan(self, model_id: str, parameters: dict, codec: str = "gpt_openai_images"):
        binding = ProviderModelBinding("b", "relay", model_id, f"relay/{model_id}", "openai_images", codec,
                                       frozenset({"generate"}))
        provider = ProviderConnection("relay", "Relay", "https://relay.example/v1", "key", 1, (binding,))
        return preview_generation_command(
            GenerationCommand("generate", model_id, "relay", "fox", parameters),
            codex_mode="images", provider_connections=[provider],
        )

    def test_history_fields_come_from_the_unified_parameters(self) -> None:
        preset = task_params_from_plan(self._plan("gpt-image-2", {
            "canvas.mode": "preset", "canvas.aspect_ratio": "9:16", "canvas.resolution": "1K",
            "gpt.quality": "high", "output.format": "webp", "gpt.output_compression": 70, "output.count": 2,
        }), main_model="")
        self.assertEqual(preset, {
            "model": "relay/gpt-image-2", "n": 2, "size": "864x1536", "ratio": "9:16", "orientation": "portrait",
            "resolution": "1K", "quality": "high", "output_format": "webp", "output_compression": 70,
        })
        auto = task_params_from_plan(self._plan("gpt-image-2", {"canvas.mode": "auto"}), main_model="gpt-5.5")
        self.assertEqual(auto, {"model": "relay/gpt-image-2", "n": 1, "size": "auto", "main_model": "gpt-5.5"})
        custom = task_params_from_plan(self._plan("gpt-image-2", {"canvas.mode": "custom", "canvas.size": "1536x1024"}), main_model="")
        self.assertEqual((custom["size"], custom["ratio"], custom["orientation"]), ("1536x1024", "3:2", "landscape"))
        self.assertNotIn("resolution", custom)

    def test_provider_sized_models_keep_ratio_and_tier_without_pixels(self) -> None:
        params = task_params_from_plan(self._plan("nano-banana-pro", {
            "canvas.aspect_ratio": "21:9", "canvas.resolution": "4K", "output.count": 1,
        }, codec="gemini_openai_images"), main_model="")
        self.assertNotIn("size", params)
        self.assertEqual((params["ratio"], params["orientation"], params["resolution"]), ("21:9", "landscape", "4K"))
        # Gemini tasks no longer carry GPT defaults such as quality or a PNG format.
        self.assertNotIn("quality", params)


if __name__ == "__main__":
    unittest.main()
