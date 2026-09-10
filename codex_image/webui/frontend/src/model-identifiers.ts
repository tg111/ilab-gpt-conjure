export const DEFAULT_GPT_IMAGE_MODEL_ID = "gpt-image-2";

export const GPT_IMAGE_MODEL_IDS = [
  DEFAULT_GPT_IMAGE_MODEL_ID,
  "gpt-image-2.5-sunburst",
  "gpt-image-2.5-flare",
] as const;

export function isGptImageModelId(value: unknown): boolean {
  return typeof value === "string" && value.startsWith("gpt-image-");
}
