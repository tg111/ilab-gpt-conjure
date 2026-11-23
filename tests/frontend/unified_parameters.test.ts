import assert from "node:assert/strict";
import test from "node:test";

import type { CatalogModel, CatalogParameterDefinition } from "../../codex_image/webui/frontend/src/types";
import {
  adoptUnifiedParameters,
  upgradeParameters,
  usesUnifiedParameters,
  valueRequirementReason,
} from "../../codex_image/webui/frontend/src/unified-parameters";
import { activeParameterValuesFor, initializeParameterDraft } from "../../codex_image/webui/frontend/src/model-parameters";

const base = { group: "generation", scope: "model", minimum: null, maximum: null, step: null, visible_when: [], operations: ["generate"], full_width: false } as const;
const definition = (id: string, extra: Partial<CatalogParameterDefinition>): CatalogParameterDefinition => ({
  ...base, id, label_key: id, control: "segmented", value_type: "string", default: "", allowed_values: [], ...extra,
} as CatalogParameterDefinition);

const unifiedGpt: CatalogModel = {
  id: "gpt-image-2", family_id: "gpt-image", display_name: "GPT Image 2", official_model_id: "gpt-image-2", version: 1,
  operations: ["generate"], input_constraints: { max_images: 16, supports_mask: true, supports_reference_files: true },
  parameter_renames: { "gpt.web_search": "tools.web_search" },
  size_spec: {
    modes: ["auto", "preset", "custom"],
    presets: { "1K": { "1:1": [1024, 1024], "3:2": [1536, 1024] }, "2K": { "16:9": [2048, 1152] } },
    custom: null,
  },
  parameters: [
    definition("canvas.mode", { control: "image_size", default: "preset", allowed_values: ["auto", "preset", "custom"] }),
    definition("canvas.aspect_ratio", { default: "1:1", allowed_values: ["1:1", "3:2", "16:9"], visible_when: [{ parameter_id: "canvas.mode", operator: "equals", value: "preset" }] }),
    definition("canvas.resolution", { default: "1K", allowed_values: ["1K", "2K"], visible_when: [{ parameter_id: "canvas.mode", operator: "equals", value: "preset" }] }),
    definition("canvas.size", { control: "text", default: "1024x1024", allowed_values: [], visible_when: [{ parameter_id: "canvas.mode", operator: "equals", value: "custom" }] }),
    definition("output.format", { default: "png", allowed_values: ["png", "jpeg", "webp"] }),
    definition("gpt.background", {
      default: "auto", allowed_values: ["auto", "transparent", "opaque"],
      value_requirements: [{ value: "transparent", condition: { parameter_id: "output.format", operator: "in", value: ["png", "webp", "svg"] }, reason: "transparent_background_requires_png_webp_or_svg" }],
    }),
    definition("tools.web_search", { control: "toggle", value_type: "boolean", default: false }),
  ],
};

test("upgrade mirrors the backend rules and is idempotent", () => {
  assert.deepEqual(upgradeParameters(unifiedGpt, { "canvas.size": "auto" }), { "canvas.mode": "auto" });
  assert.deepEqual(upgradeParameters(unifiedGpt, { "canvas.size": "2048x1152" }), {
    "canvas.mode": "preset", "canvas.aspect_ratio": "16:9", "canvas.resolution": "2K",
  });
  assert.deepEqual(upgradeParameters(unifiedGpt, { "canvas.size": "1600x896" }), { "canvas.mode": "custom", "canvas.size": "1600x896" });
  assert.deepEqual(upgradeParameters(unifiedGpt, { "gpt.web_search": true }), { "tools.web_search": true });
  const once = upgradeParameters(unifiedGpt, { "canvas.size": "1536x1024", "gpt.web_search": true });
  assert.deepEqual(upgradeParameters(unifiedGpt, once), once);
  // Without canvas.mode the model is still on its earlier form: leave values alone.
  const legacy = { ...unifiedGpt, parameters: unifiedGpt.parameters.filter((item) => item.id !== "canvas.mode") };
  assert.equal(usesUnifiedParameters(legacy), false);
  assert.deepEqual(upgradeParameters(legacy, { "canvas.size": "auto" }), { "canvas.size": "auto" });
});

test("only families on the unified form swap parameters", () => {
  const catalog = {
    parameter_renames: { "gemini-image": { "gemini.google_search": "tools.web_search" } },
    models: [
      { id: "g", family_id: "gemini-image", parameters: [definition("old", {})], unified_parameters: [definition("canvas.mode", { control: "image_size", allowed_values: ["preset"], default: "preset" })] },
      { id: "o", family_id: "gpt-image", parameters: [definition("old", {})], unified_parameters: [definition("canvas.mode", { control: "image_size", allowed_values: ["preset"], default: "preset" })] },
    ],
  };
  const adopted = adoptUnifiedParameters(catalog) as any;
  assert.equal(adopted.models[0].parameters[0].id, "canvas.mode");
  assert.deepEqual(adopted.models[0].parameter_renames, { "gemini.google_search": "tools.web_search" });
  assert.equal(adopted.models[1].parameters[0].id, "old");
  assert.equal(catalog.models[0].parameters[0].id, "old", "the payload itself is not mutated");
});

test("value requirements block a value until its condition holds", () => {
  const background = unifiedGpt.parameters.find((item) => item.id === "gpt.background")!;
  assert.equal(valueRequirementReason(unifiedGpt, background, "transparent", { "output.format": "jpeg" }), "transparent_background_requires_png_webp_or_svg");
  assert.equal(valueRequirementReason(unifiedGpt, background, "transparent", { "output.format": "webp" }), "");
  assert.equal(valueRequirementReason(unifiedGpt, background, "transparent", {}), "", "defaults to png");
  assert.equal(valueRequirementReason(unifiedGpt, background, "opaque", { "output.format": "jpeg" }), "");
  // A blocked value falls back to the default rather than being submitted.
  const draft = { "canvas.mode": "preset", "gpt.background": "transparent", "output.format": "jpeg" };
  assert.equal(activeParameterValuesFor(unifiedGpt, "generate", draft)["gpt.background"], "auto");
  assert.equal(initializeParameterDraft(unifiedGpt, draft).values["gpt.background"], "auto");
});

test("size fields follow the chosen size mode", () => {
  const preset = activeParameterValuesFor(unifiedGpt, "generate", { "canvas.mode": "preset", "canvas.aspect_ratio": "3:2", "canvas.size": "1600x896" });
  assert.equal(preset["canvas.aspect_ratio"], "3:2");
  assert.ok(!("canvas.size" in preset));
  const auto = activeParameterValuesFor(unifiedGpt, "generate", { "canvas.mode": "auto", "canvas.aspect_ratio": "3:2" });
  assert.deepEqual(Object.keys(auto).filter((key) => key.startsWith("canvas.")), ["canvas.mode"]);
});
