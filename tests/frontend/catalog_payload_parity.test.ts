import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { isGenerationCatalog } from "../../codex_image/webui/frontend/src/model-catalog";

test("real backend generation catalog payload passes the frontend validator", () => {
  const fixturePath = process.env.GENERATION_CATALOG_FIXTURE;
  assert.ok(fixturePath, "GENERATION_CATALOG_FIXTURE is required");
  const payload = JSON.parse(readFileSync(fixturePath, "utf8"));
  assert.deepEqual(
    payload.families.map((family: any) => family.id),
    ["gpt-image", "gemini-image"],
  );
  assert.equal(isGenerationCatalog(payload), true);
});

test("the real catalog's unified parameters upgrade stored drafts for every family", async () => {
  const { attachParameterRenames, upgradeParameters } = await import("../../codex_image/webui/frontend/src/unified-parameters");
  const { initializeParameterDraft, activeParameterValuesFor } = await import("../../codex_image/webui/frontend/src/model-parameters");
  const payload = attachParameterRenames(JSON.parse(readFileSync(process.env.GENERATION_CATALOG_FIXTURE!, "utf8")));
  assert.equal(isGenerationCatalog(payload), true);
  const pro = payload.models.find((model: any) => model.id === "nano-banana-pro");
  const gpt = payload.models.find((model: any) => model.id === "gpt-image-2");
  for (const model of payload.models) assert.equal(model.parameters[0].id, "canvas.mode");

  // Drafts and history saved with the earlier names keep their choices.
  const gemini = initializeParameterDraft(pro, { "canvas.aspect_ratio": "16:9", "canvas.resolution": "2K", "gemini.google_search": true });
  assert.equal(gemini.values["tools.web_search"], true);
  assert.deepEqual(gemini.dropped, []);
  const preset = initializeParameterDraft(gpt, { "canvas.size": "2048x1152", "gpt.web_search": true, "gpt.quality": "high" });
  assert.equal(preset.values["canvas.mode"], "preset");
  assert.equal(preset.values["canvas.aspect_ratio"], "16:9");
  assert.equal(preset.values["canvas.resolution"], "2K");
  assert.equal(preset.values["tools.web_search"], true);
  const custom = initializeParameterDraft(gpt, { "canvas.size": "1600x896" });
  assert.equal(custom.values["canvas.mode"], "custom");
  assert.equal(custom.values["canvas.size"], "1600x896");
  // A custom size the rules reject falls back to the default rather than being submitted.
  assert.equal(initializeParameterDraft(gpt, { "canvas.mode": "custom", "canvas.size": "1000x1008" }).values["canvas.size"], "1024x1024");
  // Only the chosen size mode's fields are submitted.
  const submitted = activeParameterValuesFor(gpt, "generate", preset.values);
  assert.equal(submitted["canvas.mode"], "preset");
  assert.ok(!("canvas.size" in submitted));
  assert.deepEqual(upgradeParameters(gpt, upgradeParameters(gpt, { "canvas.size": "auto" })), { "canvas.mode": "auto" });
});
