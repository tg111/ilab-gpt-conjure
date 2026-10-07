/** Versions sharing the GPT Image controls; Codex bindings remain Image 2 only. */
export const GPT_IMAGE_MODEL_IDS = ["gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst"] as const;

export function isGptImageModel(modelId: unknown): boolean {
  return (GPT_IMAGE_MODEL_IDS as readonly string[]).includes(String(modelId || ""));
}
