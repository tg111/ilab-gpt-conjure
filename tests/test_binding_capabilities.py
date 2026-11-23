from __future__ import annotations

import base64
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from codex_image.generation.capabilities import binding_capabilities
from codex_image.generation.catalog import get_model_manifest
from codex_image.generation.types import GenerationCommand, ImageInput
from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
from codex_image.webui.generation_request import preview_generation_command


def _png_data_url(mode: str, color: tuple) -> str:
    buffer = io.BytesIO()
    Image.new(mode, (32, 32), color).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _caps(model_id: str, protocol: str, codec: str):
    return binding_capabilities(get_model_manifest(model_id), protocol, codec)


def _preview(model_id: str, protocol: str, codec: str, parameters: dict, **command_options):
    binding = ProviderModelBinding("b", "relay", model_id, "remote", protocol, codec, frozenset({"generate", "edit"}))
    provider = ProviderConnection("relay", "Relay", "https://relay.example/v1", "key", 1, (binding,))
    command = GenerationCommand("generate", model_id, "relay", "fox", parameters, **command_options)
    return preview_generation_command(command, codex_mode="images", provider_connections=[provider])


class BindingCapabilityTests(unittest.TestCase):
    def test_parameters_are_the_model_parameters_the_protocol_can_map(self) -> None:
        images = _caps("gpt-image-2.6-flare", "openai_images", "gpt_openai_images")
        self.assertTrue(images.available)
        self.assertIn("gpt.complexity", images.parameter_ids)
        self.assertIn("gpt.frame_count", images.parameter_ids)
        self.assertTrue(images.supports_markup)
        self.assertFalse(images.uses_main_model)

        responses = _caps("gpt-image-2.5-flare", "openai_responses", "gpt_openai_responses")
        self.assertTrue(responses.uses_main_model)
        self.assertFalse(responses.supports_markup)
        self.assertIn("gpt.web_search", responses.parameter_ids)

    def test_web_search_is_only_offered_on_responses_protocols(self) -> None:
        for protocol, codec in (("openai_images", "gpt_openai_images"), ("codex_images", "gpt_codex_images")):
            with self.subTest(protocol=protocol):
                self.assertNotIn("gpt.web_search", _caps("gpt-image-2", protocol, codec).parameter_ids)
        self.assertIn("gpt.web_search", _caps("gpt-image-2", "codex_responses", "gpt_codex_responses").parameter_ids)

    def test_unusable_combinations_are_unavailable_with_a_reason(self) -> None:
        cases = {
            ("gpt-image-2.6-flare", "openai_responses", "gpt_openai_responses"): "image_feature_requires_openai_images",
            ("nano-banana-2", "openai_images", "gpt_openai_images"): "codec_family_mismatch",
            ("gpt-image-2", "openai_responses", "gpt_openai_images"): "codec_protocol_mismatch",
            ("gpt-image-2", "openai_images", "no_such_codec"): "Unknown parameter codec",
        }
        for (model, protocol, codec), reason in cases.items():
            with self.subTest(model=model, protocol=protocol, codec=codec):
                caps = _caps(model, protocol, codec)
                self.assertFalse(caps.available)
                self.assertIn(reason, caps.unavailable_reason)
                self.assertEqual(caps.parameter_ids, ())

    def test_submission_rejects_parameters_the_binding_cannot_act_on(self) -> None:
        with self.assertRaisesRegex(ValueError, "parameter_not_supported_by_binding: gpt.web_search"):
            _preview("gpt-image-2", "openai_images", "gpt_openai_images", {"gpt.web_search": True})
        # The current form always sends the switch; its default value stays accepted.
        plan = _preview("gpt-image-2", "openai_images", "gpt_openai_images", {"gpt.web_search": False})
        self.assertNotIn("tools", plan.protocol_request.json_body)

    def test_markup_needs_a_binding_that_supports_it(self) -> None:
        image = ImageInput(_png_data_url("RGB", (90, 140, 120)))
        markup = _png_data_url("RGBA", (255, 0, 0, 0))
        binding = ProviderModelBinding("b", "relay", "gpt-image-2.5-flare", "remote", "openai_responses",
                                       "gpt_openai_responses", frozenset({"generate", "edit"}))
        provider = ProviderConnection("relay", "Relay", "https://relay.example/v1", "key", 1, (binding,))
        command = GenerationCommand("edit", "gpt-image-2.5-flare", "relay", "fox", {}, image_inputs=(image,), markup_image=markup)
        with self.assertRaisesRegex(ValueError, "image_feature_requires_openai_images"):
            preview_generation_command(command, codex_mode="images", provider_connections=[provider])


class CatalogCapabilityPayloadTests(unittest.TestCase):
    def test_every_catalog_binding_carries_its_capabilities(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)
            payload = TestClient(app).get("/api/generation-catalog").json()
        codex = next(provider for provider in payload["providers"] if provider["id"] == "codex")
        by_id = {binding["id"]: binding for binding in codex["bindings"]}
        self.assertFalse(by_id["codex-gpt-image-2-images"]["capabilities"]["uses_main_model"])
        self.assertTrue(by_id["codex-gpt-image-2-responses"]["capabilities"]["uses_main_model"])
        self.assertIn("gpt.web_search", by_id["codex-gpt-image-2-responses"]["capabilities"]["parameter_ids"])
        self.assertNotIn("gpt.web_search", by_id["codex-gpt-image-2-images"]["capabilities"]["parameter_ids"])


if __name__ == "__main__":
    unittest.main()
