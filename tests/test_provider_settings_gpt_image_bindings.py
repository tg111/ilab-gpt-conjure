from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any


GPT_IMAGE_25_MODEL_IDS = ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst")


class ProviderSettingsGptImageBindingTests(unittest.TestCase):
    """Existing API providers gain GPT Image 2.5 bindings without manual setup."""

    def setUp(self) -> None:
        from codex_image.webui.provider_settings import ProviderSettings

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "api-settings.json"
        self.settings = ProviderSettings(self.path)

    @staticmethod
    def provider(provider_id: str, **binding_overrides: Any) -> dict[str, Any]:
        binding = {
            "id": f"{provider_id}-gpt",
            "canonical_model_id": "gpt-image-2",
            "remote_model_id": "vendor/gpt-image-2",
            "protocol_profile": "openai_responses",
            "parameter_codec": "gpt_openai_responses",
            "operations": ["generate", "edit"],
        }
        binding.update(binding_overrides)
        return {
            "id": provider_id,
            "name": provider_id.title(),
            "base_url": "https://relay.example/v1",
            "api_key": "secret",
            "concurrency": 2,
            "bindings": [binding],
        }

    def write_v2(self, providers: list[dict[str, Any]], defaults: dict[str, str]) -> None:
        payload = {
            "schema_version": 2,
            "codex_mode": "images",
            "active_provider_id": providers[0]["id"],
            "default_provider_by_model": defaults,
            "providers": providers,
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_existing_provider_gains_gpt_image_25_bindings_and_defaults(self) -> None:
        self.write_v2(
            [self.provider("relay"), self.provider("backup")],
            {"gpt-image-2": "backup"},
        )

        settings = self.settings.read()

        for provider in settings["providers"]:
            bindings = {binding["canonical_model_id"]: binding for binding in provider["bindings"]}
            self.assertEqual(set(bindings), {"gpt-image-2", *GPT_IMAGE_25_MODEL_IDS})
            self.assertEqual(bindings["gpt-image-2"]["remote_model_id"], "vendor/gpt-image-2")
            for model_id in GPT_IMAGE_25_MODEL_IDS:
                self.assertEqual(bindings[model_id]["id"], f"{provider['id']}-{model_id}".replace(".", "-"))
                self.assertEqual(bindings[model_id]["remote_model_id"], model_id)
                self.assertEqual(bindings[model_id]["protocol_profile"], "openai_responses")
                self.assertEqual(bindings[model_id]["parameter_codec"], "gpt_openai_responses")
        # New models follow the provider already chosen for GPT Image 2.
        self.assertEqual(
            settings["default_provider_by_model"],
            {"gpt-image-2": "backup", **{model_id: "backup" for model_id in GPT_IMAGE_25_MODEL_IDS}},
        )

    def test_upgrade_happens_in_memory_until_the_next_save(self) -> None:
        self.write_v2([self.provider("relay")], {"gpt-image-2": "relay"})
        before = self.path.read_text(encoding="utf-8")

        upgraded = self.settings.read()
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

        self.settings.write(upgraded)
        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["catalog_binding_version"], 1)
        self.assertEqual(len(persisted["providers"][0]["bindings"]), 3)

    def test_upgrade_keeps_an_existing_valid_gpt_image_25_default(self) -> None:
        backup = self.provider("backup")
        backup["bindings"].append({
            "id": "backup-flare",
            "canonical_model_id": "gpt-image-2.5-flare",
            "remote_model_id": "vendor/flare",
            "protocol_profile": "openai_images",
            "parameter_codec": "gpt_openai_images",
            "operations": ["generate", "edit"],
        })
        self.write_v2(
            [self.provider("relay"), backup],
            {"gpt-image-2": "relay", "gpt-image-2.5-flare": "backup"},
        )

        settings = self.settings.read()

        self.assertEqual(settings["default_provider_by_model"]["gpt-image-2.5-flare"], "backup")
        self.assertEqual(settings["default_provider_by_model"]["gpt-image-2.5-sunburst"], "relay")
        flare = [
            binding for binding in settings["providers"][1]["bindings"]
            if binding["canonical_model_id"] == "gpt-image-2.5-flare"
        ]
        self.assertEqual([binding["remote_model_id"] for binding in flare], ["vendor/flare"])

    def test_saved_bindings_are_not_upgraded_again(self) -> None:
        # A user who removes the 2.5 bindings keeps them removed after saving.
        self.settings.write({
            "schema_version": 2,
            "codex_mode": "images",
            "active_provider_id": "relay",
            "default_provider_by_model": {"gpt-image-2": "relay"},
            "providers": [self.provider("relay")],
        })

        settings = self.settings.read()

        self.assertEqual(
            [binding["canonical_model_id"] for binding in settings["providers"][0]["bindings"]],
            ["gpt-image-2"],
        )
        self.assertEqual(settings["default_provider_by_model"], {"gpt-image-2": "relay"})

    def test_upgrade_copies_transport_options_from_gpt_image_2_binding(self) -> None:
        self.write_v2(
            [self.provider("relay", append_aspect_ratio_prompt=True, transparency_mode="prompt")],
            {"gpt-image-2": "relay"},
        )

        bindings = self.settings.read()["providers"][0]["bindings"]

        for binding in bindings:
            self.assertTrue(binding.get("append_aspect_ratio_prompt"), binding["id"])
            self.assertEqual(binding.get("transparency_mode"), "prompt", binding["id"])

    def test_default_settings_bind_every_gpt_image_version(self) -> None:
        settings = self.settings.read()

        model_ids = [binding["canonical_model_id"] for binding in settings["providers"][0]["bindings"]]
        self.assertEqual(model_ids, ["gpt-image-2", *GPT_IMAGE_25_MODEL_IDS])
        self.assertEqual(
            settings["default_provider_by_model"],
            {model_id: "default" for model_id in model_ids},
        )


if __name__ == "__main__":
    unittest.main()
