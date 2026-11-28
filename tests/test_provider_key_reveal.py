from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from codex_image.webui.provider_settings import ProviderSettings
from codex_image.webui.routes.settings import register_settings_routes


def provider(provider_id: str, api_key: str) -> dict:
    return {
        "id": provider_id,
        "name": provider_id,
        "base_url": "https://relay.example/v1",
        "api_key": api_key,
        "concurrency": 2,
        "bindings": [{
            "id": f"{provider_id}-gpt",
            "canonical_model_id": "gpt-image-2",
            "remote_model_id": "gpt-image-2",
            "protocol_profile": "openai_images",
            "parameter_codec": "gpt_openai_images",
            "operations": ["generate", "edit"],
        }],
    }


class ProviderKeyRevealTests(unittest.TestCase):
    """The settings list stays masked; one explicit request shows one saved key."""

    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.settings = ProviderSettings(Path(temp_dir.name) / "api-settings.json")
        self.settings.write({
            "schema_version": 2,
            "codex_mode": "images",
            "active_provider_id": "relay",
            "default_provider_by_model": {"gpt-image-2": "relay"},
            "providers": [provider("relay", "sk-saved-test-key-1234"), provider("empty", "sk-other-test-key-9876")],
        })
        app = FastAPI()
        register_settings_routes(app, SimpleNamespace(route_helpers={}, api_settings=self.settings))
        self.client = TestClient(app)

    def test_saved_key_is_returned_for_exactly_the_requested_provider(self) -> None:
        response = self.client.post("/api/api-settings/reveal-key", json={"provider_id": "relay"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"api_key": "sk-saved-test-key-1234"})
        self.assertEqual(response.headers["cache-control"], "no-store")
        other = self.client.post("/api/api-settings/reveal-key", json={"provider_id": "empty"})
        self.assertEqual(other.json(), {"api_key": "sk-other-test-key-9876"})

    def test_unknown_provider_never_falls_back_to_the_active_one(self) -> None:
        for payload in ({"provider_id": "missing"}, {"provider_id": ""}, {}):
            response = self.client.post("/api/api-settings/reveal-key", json=payload)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("sk-saved", response.text)

    def test_reading_keys_is_not_a_get_and_the_list_stays_masked(self) -> None:
        self.assertEqual(self.client.get("/api/api-settings/reveal-key").status_code, 405)
        listing = self.client.get("/api/api-settings").text
        self.assertNotIn("sk-saved-test-key-1234", listing)
        self.assertIn("api_key_masked", json.loads(listing)["settings"]["providers"][0])


if __name__ == "__main__":
    unittest.main()
