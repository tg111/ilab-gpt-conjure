import assert from "node:assert/strict";
import test from "node:test";
import {
  discoveryProtocolForBaseUrl,
  matchCatalogModel,
  templateForDiscoveredModel,
} from "../../codex_image/webui/frontend/src/provider-discovery-panel";
import type { CatalogModel, ProviderModelBindingSettings } from "../../codex_image/webui/frontend/src/types";

const model = (id: string, official: string) => ({ id, official_model_id: official, display_name: id }) as CatalogModel;
const models = [
  model("gpt-image-2", "gpt-image-2"),
  model("gpt-image-2.5-flare", "gpt-image-2.5-flare"),
  model("nano-banana-pro", "gemini-3-pro-image"),
  model("nano-banana-2", "gemini-3.1-flash-image"),
  model("nano-banana-2-lite", "gemini-3.1-flash-lite-image"),
];

test("provider model names map to catalog models by id or official id", () => {
  assert.equal(matchCatalogModel("gpt-image-2", models), "gpt-image-2");
  assert.equal(matchCatalogModel("gpt-image-2.5-flare", models), "gpt-image-2.5-flare");
  assert.equal(matchCatalogModel("google/gemini-3-pro-image-preview", models), "nano-banana-pro");
  assert.equal(matchCatalogModel("gemini-3.1-flash-image:free", models), "nano-banana-2");
  assert.equal(matchCatalogModel("nano-banana-2-lite", models), "nano-banana-2-lite");
  assert.equal(matchCatalogModel("NANO-BANANA-2", models), "nano-banana-2");
});

test("names that only share a prefix are not matched", () => {
  assert.equal(matchCatalogModel("gpt-image-25", models), "");
  assert.equal(matchCatalogModel("text-model", models), "");
  assert.equal(matchCatalogModel("vendor/custom.image:2", models), "");
});

test("native Gemini endpoints list models with the Gemini protocol", () => {
  assert.equal(discoveryProtocolForBaseUrl("https://generativelanguage.googleapis.com/v1beta"), "gemini");
  assert.equal(discoveryProtocolForBaseUrl("https://relay.example/v1beta/"), "gemini");
  assert.equal(discoveryProtocolForBaseUrl("https://generativelanguage.googleapis.com/v1beta/openai"), "openai_images");
  assert.equal(discoveryProtocolForBaseUrl("https://relay.example/v1"), "openai_images");
  assert.equal(discoveryProtocolForBaseUrl("not a url"), "openai_images");
});

test("new bindings reuse the protocol the provider already uses for that family", () => {
  const t8: ProviderModelBindingSettings = {
    id: "a", canonical_model_id: "nano-banana-pro", remote_model_id: "x",
    protocol_profile: "t8_images", parameter_codec: "gemini_t8_images", operations: ["generate", "edit"],
  };
  assert.equal(templateForDiscoveredModel("nano-banana-2", "https://relay.example/v1", [t8]), "gemini_t8_images");
  // Without a sibling, the base URL decides.
  assert.equal(templateForDiscoveredModel("nano-banana-2", "https://relay.example/v1", []), "gemini_openai_images");
  assert.equal(templateForDiscoveredModel("nano-banana-2", "https://generativelanguage.googleapis.com/v1beta", []), "gemini_generate_content");
  assert.equal(templateForDiscoveredModel("gpt-image-2", "https://relay.example/v1", [t8]), "gpt_openai_images");
});
