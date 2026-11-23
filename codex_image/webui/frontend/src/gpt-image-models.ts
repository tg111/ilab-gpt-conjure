/**
 * GPT Image models share one provider menu and the GPT summary layout. The
 * family is recognised by its id prefix, so new GPT Image versions need no
 * frontend change.
 */
export function isGptImageModel(modelId: unknown): boolean {
  return String(modelId || "").startsWith("gpt-image-");
}
