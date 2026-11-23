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

test("Gemini models use the unified parameters from the real catalog; GPT keeps its form", async () => {
  const { adoptUnifiedParameters, upgradeParameters } = await import("../../codex_image/webui/frontend/src/unified-parameters");
  const { initializeParameterDraft, activeParameterValuesFor } = await import("../../codex_image/webui/frontend/src/model-parameters");
  const payload = adoptUnifiedParameters(JSON.parse(readFileSync(process.env.GENERATION_CATALOG_FIXTURE!, "utf8")));
  assert.equal(isGenerationCatalog(payload), true);
  const pro = payload.models.find((model: any) => model.id === "nano-banana-pro");
  const gpt = payload.models.find((model: any) => model.id === "gpt-image-2");
  assert.equal(pro.parameters[0].id, "canvas.mode");
  assert.ok(pro.parameters.some((parameter: any) => parameter.id === "tools.web_search"));
  assert.deepEqual(pro.parameter_renames, { "gemini.google_search": "tools.web_search" });
  assert.ok(gpt.parameters.some((parameter: any) => parameter.id === "gpt.web_search"));
  assert.ok(!gpt.parameters.some((parameter: any) => parameter.id === "canvas.mode"));

  // A draft or history task saved with the earlier names keeps its choices.
  const stored = { "canvas.aspect_ratio": "16:9", "canvas.resolution": "2K", "gemini.google_search": true };
  const draft = initializeParameterDraft(pro, stored);
  assert.equal(draft.values["tools.web_search"], true);
  assert.equal(draft.values["canvas.mode"], "preset");
  assert.deepEqual(draft.dropped, []);
  assert.deepEqual(activeParameterValuesFor(pro, "generate", draft.values), {
    "canvas.mode": "preset",
    "canvas.aspect_ratio": "16:9",
    "canvas.resolution": "2K",
    "output.count": 1,
    "gemini.safety_settings": pro.parameters.find((parameter: any) => parameter.id === "gemini.safety_settings").default,
    "tools.web_search": true,
  });
  // GPT drafts are not touched until GPT moves to the unified form.
  assert.deepEqual(upgradeParameters(gpt, { "canvas.size": "auto", "gpt.web_search": true }), { "canvas.size": "auto", "gpt.web_search": true });
});
