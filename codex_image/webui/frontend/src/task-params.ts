import { currentApiImagesConcurrency, currentApiMode, currentApiProviderId, currentCodexMode } from "./api-provider-settings";
import { currentAuthSource } from "./auth-source";
import { currentMainModel } from "./main-model-combobox";
import { activeParameterValues } from "./model-parameters";
import { selectedProviderBinding } from "./provider-selection";
import { requestedSize } from "./image-size-editor";
import { getLegacyBridge } from "./state";

function orientation(ratio: string): string {
  const [width, height] = ratio.split(":").map(Number);
  if (!width || !height || width === height) return width && height ? "square" : "";
  return width > height ? "landscape" : "portrait";
}

/**
 * Task fields shown on the pending card, in the request preview and in the
 * output lock summary. Derived from the selected model's parameters; the
 * submitted request carries the parameters themselves.
 */
export function currentTaskParams(): Record<string, unknown> {
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
  const parameters = model ? activeParameterValues(model) : {};
  const binding = selectedProviderBinding();
  const params: Record<string, unknown> = {
    model: binding?.remote_model_id || model?.id || "",
    n: parameters["output.count"] ?? 1,
  };
  const size = requestedSize(model, parameters);
  if (size) params.size = size;
  const ratio = String(parameters["canvas.aspect_ratio"] || "");
  if (ratio && parameters["canvas.mode"] !== "auto") {
    params.ratio = ratio;
    params.orientation = orientation(ratio);
  }
  if (parameters["canvas.resolution"] && parameters["canvas.mode"] !== "auto") params.resolution = parameters["canvas.resolution"];
  const copies: Array<[string, string]> = [
    ["gpt.quality", "quality"], ["gpt.background", "background"], ["output.format", "output_format"],
    ["gpt.moderation", "moderation"], ["gpt.output_compression", "output_compression"],
    ["gpt.complexity", "complexity"], ["gpt.frame_count", "frame_count"],
    ["gpt.frame_duration_ms", "frame_duration_ms"],
  ];
  copies.forEach(([id, field]) => {
    if (id in parameters) params[field] = parameters[id];
  });
  if (parameters["tools.web_search"]) params.web_search = true;
  if (binding?.capabilities?.uses_main_model) params.main_model = currentMainModel();
  if (currentAuthSource() === "api") {
    params.api_provider_id = currentApiProviderId();
    params.api_mode = currentApiMode();
    params.api_images_concurrency = currentApiImagesConcurrency();
  } else if (currentAuthSource() === "codex") {
    params.codex_mode = currentCodexMode();
  }
  return params;
}
