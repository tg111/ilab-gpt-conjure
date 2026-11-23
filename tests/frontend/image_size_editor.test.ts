import assert from "node:assert/strict";
import test from "node:test";

import type { CatalogCustomSizeRules, CatalogModel } from "../../codex_image/webui/frontend/src/types";

(globalThis as any).window ??= { __codexImageWebUI: { state: {}, els: {}, methods: {} } };
const { customSizeError, parsePixelSize, requestedSize, suggestLegalSize } = await import("../../codex_image/webui/frontend/src/image-size-editor");

// The GPT rules served by the catalog (GPT_SIZE_SPEC.custom).
const RULES: CatalogCustomSizeRules = {
  min_edge: 16, max_edge: 3840, multiple: 16, max_aspect_ratio: 3,
  min_pixels: 655360, max_pixels: 8294400, relaxed_formats: ["gif"],
};

test("custom size errors match the backend's custom_size_error", () => {
  const cases: Record<string, string> = {
    "1600x896": "",
    "1600 x 896": "custom_size_invalid_format",
    "8x1024": "custom_size_out_of_bounds",
    "4096x1024": "custom_size_out_of_bounds",
    "1000x1008": "custom_size_not_multiple",
    "3840x1024": "custom_size_ratio_too_large",
    "512x512": "custom_size_pixels_out_of_range",
    "3840x3840": "custom_size_pixels_out_of_range",
  };
  for (const [size, error] of Object.entries(cases)) assert.equal(customSizeError(RULES, size, "png"), error, size);
  // GIF skips ratio and pixel limits but keeps the grid.
  assert.equal(customSizeError(RULES, "512x512", "gif"), "");
  assert.equal(customSizeError(RULES, "3840x1024", "gif"), "");
  assert.equal(customSizeError(RULES, "1000x1008", "gif"), "custom_size_not_multiple");
  assert.equal(customSizeError(RULES, undefined, "png"), "custom_size_invalid_format");
  assert.deepEqual(parsePixelSize(" 1024x768 "), { width: 1024, height: 768 });
  assert.equal(parsePixelSize("1024×768"), null);
});

test("the suggested size is always legal and keeps the requested shape", () => {
  for (const [width, height] of [[1000, 1008], [512, 512], [3840, 3840], [5000, 1000], [100, 4000], [0, 0], [NaN, 900], [1920, 1080]]) {
    const suggestion = suggestLegalSize(RULES, width, height);
    const size = `${suggestion.width}x${suggestion.height}`;
    assert.equal(customSizeError(RULES, size, "png"), "", `${width}x${height} -> ${size}`);
  }
  // A legal size is suggested unchanged; a near miss lands next to it.
  assert.deepEqual(suggestLegalSize(RULES, 1600, 896), { width: 1600, height: 896 });
  assert.deepEqual(suggestLegalSize(RULES, 1000, 1008), { width: 1008, height: 1008 });
  const wide = suggestLegalSize(RULES, 1920, 1080);
  assert.ok(Math.abs(wide.width / wide.height - 16 / 9) < 0.02, `${wide.width}x${wide.height}`);
  // Too wide a ratio is clamped to the maximum.
  const clamped = suggestLegalSize(RULES, 6000, 1000);
  assert.ok(clamped.width / clamped.height <= RULES.max_aspect_ratio);
});

test("the requested size follows the size mode", () => {
  const model = {
    id: "gpt-image-2",
    size_spec: { modes: ["auto", "preset", "custom"], presets: { "2K": { "16:9": [2048, 1152] } }, custom: RULES },
  } as unknown as CatalogModel;
  const preset = { "canvas.mode": "preset", "canvas.aspect_ratio": "16:9", "canvas.resolution": "2K" };
  assert.equal(requestedSize(model, { ...preset, "canvas.resolution": "4K" }), "", "an unknown preset has no pixels");
  assert.equal(requestedSize(model, preset), "2048x1152");
  assert.equal(requestedSize(model, { "canvas.mode": "auto", "canvas.size": "1600x896" }), "auto");
  assert.equal(requestedSize(model, { "canvas.mode": "custom", "canvas.size": "1600x896" }), "1600x896");
  // Providers that size the image themselves (Gemini) have no preset pixels.
  assert.equal(requestedSize({ ...model, size_spec: { modes: ["preset"], presets: {}, custom: null } } as any, preset), "");
});

test("GIF frames are capped by the canvas pixel budget and the supplier's edit limit", async () => {
  const { gifFrameLimit } = await import("../../codex_image/webui/frontend/src/image-size-editor");
  const model = {
    id: "gpt-image-2.6-flare",
    size_spec: { modes: ["auto", "preset", "custom"], presets: { "1K": { "1:1": [1024, 1024] } }, custom: RULES },
  } as unknown as CatalogModel;
  const custom = (size: string) => ({ "canvas.mode": "custom", "canvas.size": size });
  assert.equal(gifFrameLimit(model, 64, custom("512x512"), null), 64, "a small canvas keeps the catalog maximum");
  assert.equal(gifFrameLimit(model, 64, custom("3840x3840"), null), 9, "128 MiB / 3840² pixels");
  assert.equal(gifFrameLimit(model, 64, { "canvas.mode": "preset", "canvas.aspect_ratio": "1:1", "canvas.resolution": "1K" }, null), 64);
  assert.equal(gifFrameLimit(model, 64, custom("512x512"), 16), 16, "official GIF edits allow 16 frames");
  assert.equal(gifFrameLimit(model, 64, { "canvas.mode": "auto" }, null), 64, "auto size has no pixel budget");
  assert.equal(gifFrameLimit(model, null, { "canvas.mode": "auto" }, null), null);
  assert.equal(gifFrameLimit(model, 64, custom("3840x3840"), 1), 2, "never below the minimum frame count");
});
