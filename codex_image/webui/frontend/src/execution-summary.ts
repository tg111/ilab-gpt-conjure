import { currentGenerationSelection } from "./generation-request";
import { requestedSize } from "./image-size-editor";
import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";
export function updateExecutionSummary(): void {
  const element = document.getElementById("executionSummary");
  if (!element) return;
  const selection = currentGenerationSelection();
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find(item => item.id === selection.canonicalModelId);
  const provider = state.generationCatalog?.providers.find(item => item.id === selection.providerId);
  const p = selection.parameters;
  // Pixels when the size is known; the ratio and tier when the provider sizes the image.
  const requested = requestedSize(model, p);
  const pixels = requested === "auto" ? translate("output.sizeAuto") : requested.replace(/^(\d+)x(\d+)$/, "$1 × $2");
  const size = pixels || String(p["canvas.aspect_ratio"] || "");
  const resolution = pixels ? "" : String(p["output.resolution"] || p["canvas.resolution"] || "");
  element.textContent = [translate("ux.execution"), model?.display_name || translate("modelSelection.providerUnavailable"), provider?.name, size, resolution, formatTranslation("ux.imageCount", { count: Number(p["output.count"] || 1) }), p["gpt.background"] === "transparent" ? translate("output.transparentBackground") : ""].filter(Boolean).join(" · ");
  element.title = element.textContent;
  element.dataset.modelId = selection.canonicalModelId;
  element.dataset.providerId = selection.providerId;
  element.dataset.parameters = JSON.stringify(p);
}
