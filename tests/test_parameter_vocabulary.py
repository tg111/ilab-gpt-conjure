from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_image.generation.catalog import GPT_SIZE_PRESETS, GPT_SIZE_SPEC, get_model_manifest, list_model_manifests
from codex_image.generation.parameter_vocabulary import (
    custom_size_error,
    requested_image_size,
    upgrade_parameters,
)
from codex_image.generation.types import GenerationCommand
from codex_image.providers.contracts import ProviderConnection, ProviderModelBinding
from codex_image.webui.generation_request import preview_generation_command


def _preview(model_id: str, parameters: dict, protocol: str = "openai_images", codec: str = "gpt_openai_images"):
    binding = ProviderModelBinding("b", "relay", model_id, "remote", protocol, codec, frozenset({"generate", "edit"}))
    provider = ProviderConnection("relay", "Relay", "https://relay.example/v1", "key", 1, (binding,))
    command = GenerationCommand("generate", model_id, "relay", "fox", parameters)
    return preview_generation_command(command, codex_mode="images", provider_connections=[provider])


class UpgradeParametersTests(unittest.TestCase):
    def test_gpt_sizes_become_size_mode_choices(self) -> None:
        self.assertEqual(upgrade_parameters("gpt-image-2", {"canvas.size": "auto"}), {"canvas.mode": "auto"})
        self.assertEqual(
            upgrade_parameters("gpt-image-2", {"canvas.size": "2048x1152"}),
            {"canvas.mode": "preset", "canvas.aspect_ratio": "16:9", "canvas.resolution": "2K"},
        )
        self.assertEqual(
            upgrade_parameters("gpt-image-2", {"canvas.size": "1600x896"}),
            {"canvas.mode": "custom", "canvas.size": "1600x896"},
        )

    def test_every_preset_round_trips_to_the_same_pixels(self) -> None:
        for resolution, ratios in GPT_SIZE_PRESETS.items():
            for ratio, (width, height) in ratios.items():
                with self.subTest(resolution=resolution, ratio=ratio):
                    size = f"{width}x{height}"
                    upgraded = upgrade_parameters("gpt-image-2.5-flare", {"canvas.size": size})
                    self.assertEqual(upgraded["canvas.aspect_ratio"], ratio)
                    self.assertEqual(upgraded["canvas.resolution"], resolution)
                    self.assertEqual(requested_image_size("gpt-image-2.5-flare", upgraded), size)

    def test_upgrade_is_idempotent(self) -> None:
        for model, parameters in (
            ("gpt-image-2", {"canvas.size": "1536x1024", "gpt.web_search": True, "gpt.quality": "high"}),
            ("gpt-image-2", {"canvas.size": "auto"}),
            ("gpt-image-2", {"canvas.size": "1600x896"}),
            ("nano-banana-pro", {"canvas.aspect_ratio": "16:9", "gemini.google_search": True}),
        ):
            with self.subTest(model=model, parameters=parameters):
                once = upgrade_parameters(model, parameters)
                self.assertEqual(upgrade_parameters(model, once), once)

    def test_web_search_is_renamed_per_family_only_where_the_model_has_it(self) -> None:
        self.assertEqual(upgrade_parameters("gpt-image-2", {"gpt.web_search": True}), {"tools.web_search": True})
        self.assertEqual(upgrade_parameters("nano-banana-2", {"gemini.google_search": True}), {"tools.web_search": True})
        # Lite has no search; the unknown id keeps its name so the error names it.
        self.assertEqual(upgrade_parameters("nano-banana-2-lite", {"gemini.google_search": True}), {"gemini.google_search": True})
        # Another family's id is not translated.
        self.assertEqual(upgrade_parameters("gpt-image-2", {"gemini.google_search": True}), {"gemini.google_search": True})

    def test_parameters_without_a_size_choose_no_size(self) -> None:
        upgraded = upgrade_parameters("gpt-image-2", {"gpt.quality": "low"})
        self.assertNotIn("canvas.mode", upgraded)
        self.assertIsNone(requested_image_size("gpt-image-2", upgraded))
        self.assertEqual(requested_image_size("gpt-image-2", {"canvas.mode": "preset"}), "1024x1024")

    def test_gemini_parameters_only_rename_search(self) -> None:
        parameters = {"canvas.aspect_ratio": "21:9", "canvas.resolution": "4K", "output.count": 3}
        self.assertEqual(upgrade_parameters("nano-banana-pro", parameters), parameters)


class CustomSizeRuleTests(unittest.TestCase):
    def test_rules_match_the_previous_form_validation(self) -> None:
        cases = {
            "1600x896": None,
            "1600 x 896": "custom_size_invalid_format",
            "8x1024": "custom_size_out_of_bounds",
            "4096x1024": "custom_size_out_of_bounds",
            "1000x1008": "custom_size_not_multiple",
            "3840x1024": "custom_size_ratio_too_large",
            "512x512": "custom_size_pixels_out_of_range",
            "3840x3840": "custom_size_pixels_out_of_range",
        }
        for size, error in cases.items():
            with self.subTest(size=size):
                self.assertEqual(custom_size_error(GPT_SIZE_SPEC, size, "png"), error)

    def test_gif_skips_ratio_and_pixel_limits(self) -> None:
        self.assertIsNone(custom_size_error(GPT_SIZE_SPEC, "512x512", "gif"))
        self.assertIsNone(custom_size_error(GPT_SIZE_SPEC, "3840x1024", "gif"))
        self.assertEqual(custom_size_error(GPT_SIZE_SPEC, "1000x1008", "gif"), "custom_size_not_multiple")

    def test_submissions_are_checked_against_the_rules(self) -> None:
        with self.assertRaisesRegex(ValueError, "custom_size_not_multiple: canvas.size"):
            _preview("gpt-image-2", {"canvas.size": "1000x1008"})
        with self.assertRaisesRegex(ValueError, "custom_size_pixels_out_of_range: canvas.size"):
            _preview("gpt-image-2", {"canvas.mode": "custom", "canvas.size": "512x512"})
        plan = _preview("gpt-image-2.6-flare", {"canvas.mode": "custom", "canvas.size": "512x512", "output.format": "gif"})
        self.assertEqual(plan.protocol_request.json_body["size"], "512x512")

    def test_preset_fields_are_rejected_outside_preset_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "Parameter is not applicable: canvas.aspect_ratio"):
            _preview("gpt-image-2", {"canvas.mode": "auto", "canvas.aspect_ratio": "1:1"})
        with self.assertRaisesRegex(ValueError, "Parameter is not applicable: canvas.size"):
            _preview("gpt-image-2", {"canvas.mode": "preset", "canvas.size": "1600x896"})


class ValueRequirementTests(unittest.TestCase):
    def test_transparent_background_needs_a_format_with_alpha(self) -> None:
        with self.assertRaisesRegex(ValueError, "transparent_background_requires_png_webp_or_svg: gpt.background"):
            _preview("gpt-image-2", {"gpt.background": "transparent", "output.format": "jpeg"})
        for output_format in ("png", "webp"):
            with self.subTest(output_format=output_format):
                _preview("gpt-image-2", {"gpt.background": "transparent", "output.format": output_format})
        _preview("gpt-image-2", {"gpt.background": "opaque", "output.format": "jpeg"})


class CatalogVocabularyTests(unittest.TestCase):
    def test_every_model_describes_its_size(self) -> None:
        for model in list_model_manifests():
            with self.subTest(model=model.id):
                self.assertIsNotNone(model.size_spec)
                mode = model.parameter("canvas.mode")
                self.assertEqual(mode.control, "image_size")
                self.assertEqual(mode.allowed_values, model.size_spec.modes)
                self.assertEqual(len(mode.value_label_keys), len(mode.allowed_values))
        self.assertEqual(get_model_manifest("nano-banana-pro").size_spec.modes, ("preset",))

    def test_catalog_api_serves_the_unified_parameters(self) -> None:
        from fastapi.testclient import TestClient

        from codex_image.webui.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(output_root=Path(tmp), auth_checker=lambda: True, auto_start_queue=False)
            payload = TestClient(app).get("/api/generation-catalog").json()
        gpt = payload["models"][0]
        ids = [parameter["id"] for parameter in gpt["parameters"]]
        self.assertEqual(ids[:4], ["canvas.mode", "canvas.aspect_ratio", "canvas.resolution", "canvas.size"])
        self.assertIn("tools.web_search", ids)
        self.assertNotIn("gpt.web_search", ids)
        self.assertNotIn("unified_parameters", gpt)
        size = next(parameter for parameter in gpt["parameters"] if parameter["id"] == "canvas.size")
        self.assertEqual(size["control"], "pixel_size")
        quality = next(parameter for parameter in gpt["parameters"] if parameter["id"] == "gpt.quality")
        self.assertEqual(quality["value_label_keys"][0], "output.qualityAuto")
        self.assertEqual(gpt["size_spec"]["modes"], ["auto", "preset", "custom"])
        self.assertEqual(gpt["size_spec"]["presets"]["4K"]["16:9"], [3840, 2160])
        self.assertEqual(payload["parameter_renames"]["gpt-image"], {"gpt.web_search": "tools.web_search"})

if __name__ == "__main__":
    unittest.main()
