import type { CatalogModel, CatalogParameterDefinition, GenerationOperation } from "./types";
import { selectedProviderBinding } from "./provider-selection";
import { isGptImageModelId } from "./model-identifiers";
import { getLegacyBridge } from "./state";
import { renderCurrentModelParameters } from "./model-parameters";

function cloneValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneValue(item)]));
  }
  return value;
}

export function canonicalControlValues(
  taskParams: Record<string, unknown>,
  protocolProfile: string,
): Record<string, unknown> {
  const format = String(taskParams.output_format || "png");
  const values: Record<string, unknown> = {
    "canvas.size": taskParams.size,
    "canvas.aspect_ratio": taskParams.ratio,
    "canvas.resolution": taskParams.resolution,
    "gpt.quality": taskParams.quality,
    "gpt.background": taskParams.background ?? "auto",
    "output.format": format,
    "gpt.moderation": taskParams.moderation,
    "gpt.web_search": protocolProfile.endsWith("_responses") && Boolean(taskParams.web_search),
    "output.count": taskParams.n,
  };
  if (format === "jpeg" || format === "webp") {
    values["gpt.output_compression"] = taskParams.output_compression;
  }
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value !== undefined && value !== null));
}

function conditionMatches(
  condition: CatalogParameterDefinition["visible_when"][number],
  values: Record<string, unknown>,
): boolean {
  const actual = values[condition.parameter_id];
  if (condition.operator === "equals") return actual === condition.value;
  if (condition.operator === "not_equals") return actual !== condition.value;
  return Array.isArray(condition.value) && condition.value.includes(actual);
}

function parameterValueValid(parameter: CatalogParameterDefinition, value: unknown): boolean {
  const typeValid = parameter.value_type === "string" ? typeof value === "string"
    : parameter.value_type === "integer" ? typeof value === "number" && Number.isInteger(value)
      : parameter.value_type === "boolean" ? typeof value === "boolean"
        : parameter.value_type === "object" ? Boolean(value) && typeof value === "object" && !Array.isArray(value)
          : false;
  if (!typeValid) return false;
  if (parameter.allowed_values.length && !parameter.allowed_values.includes(value)) return false;
  if (typeof value === "number") {
    if (parameter.minimum !== null && value < parameter.minimum) return false;
    if (parameter.maximum !== null && value > parameter.maximum) return false;
    if (parameter.step !== null) {
      const base = parameter.minimum ?? 0;
      const quotient = (value - base) / parameter.step;
      if (Math.abs(quotient - Math.round(quotient)) > 1e-9) return false;
    }
  }
  return true;
}

export function migratePortableModelDraft(
  sourceModel: CatalogModel,
  targetModel: CatalogModel,
  sourceDraft: Record<string, unknown>,
  targetDraft: Record<string, unknown>,
): Record<string, unknown> {
  const sourceIds = new Set(sourceModel.parameters.map((definition) => definition.id));
  return Object.fromEntries(targetModel.parameters.map((definition) => {
    // Canonical legacy controls can expose portable values (for example
    // aspect ratio and resolution) even when the source manifest names those
    // controls differently. Carry a valid portable value before falling back
    // to the target model's saved draft.
    const rawSourceValue = sourceDraft[definition.id];
    const sourceValue = definition.id === "canvas.resolution" && typeof rawSourceValue === "string"
      ? rawSourceValue.toLowerCase() === "standard" || rawSourceValue === "1k"
        ? "1K"
        : rawSourceValue.toLowerCase() === "2k" ? "2K"
          : rawSourceValue.toLowerCase() === "4k" ? "4K" : rawSourceValue
      : rawSourceValue;
    if (sourceValue !== undefined && parameterValueValid(definition, sourceValue)) {
      return [definition.id, cloneValue(sourceValue)];
    }
    if (sourceIds.has(definition.id)) {
      return [definition.id, cloneValue(definition.default)];
    }
    const targetValue = targetDraft[definition.id];
    return [definition.id, cloneValue(
      parameterValueValid(definition, targetValue) ? targetValue : definition.default,
    )];
  }));
}

export function canonicalParametersForSubmission(
  model: CatalogModel,
  operation: GenerationOperation,
  draft: Record<string, unknown>,
  currentValues: Record<string, unknown>,
): Record<string, unknown> {
  const values = Object.fromEntries(model.parameters.map((parameter) => {
    const draftValue = draft[parameter.id];
    const baseValue = parameterValueValid(parameter, draftValue) ? draftValue : parameter.default;
    const currentValue = currentValues[parameter.id];
    return [parameter.id, parameterValueValid(parameter, currentValue) ? currentValue : baseValue];
  }));
  return Object.fromEntries(model.parameters
    .filter((parameter) => parameter.operations.includes(operation))
    .filter((parameter) => parameter.visible_when.every((condition) => conditionMatches(condition, values)))
    .map((parameter) => [parameter.id, values[parameter.id] ?? parameter.default]));
}

function selectedTaskIsCompleted(state: any): boolean {
  const selectedTask = state.tasks?.find((task: any) => (
    String(task?.task_id) === String(state.selectedTaskId)
  ));
  return selectedTask?.status === "completed";
}

export function saveCurrentModelParameterDraft(
  options: { preserveCompletedTaskDraft?: boolean } = {},
): void {
  const { state, methods } = getLegacyBridge();
  // Applying a completed task dispatches normal form events.  Those events
  // must not turn the task's historical values into a saved model draft.
  if (state.applyingCompletedTaskOutputSettings) return;
  // A model switch is not an explicit edit to the completed task.  Preserve
  // the existing draft for the model being left, while normal user edits keep
  // saving as usual.
  if (options.preserveCompletedTaskDraft && selectedTaskIsCompleted(state)) return;
  const model = state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
  if (!model || typeof methods.currentTaskParams !== "function") return;
  if (!isGptImageModelId(model.id)) {
    methods.persistModelSelection?.();
    return;
  }
  const values = canonicalControlValues(methods.currentTaskParams(), selectedProviderBinding()?.protocol_profile || "");
  const allowed = new Set(model.parameters.map((parameter) => parameter.id));
  state.parameterDraftsByModel[model.id] = {
    ...(state.parameterDraftsByModel[model.id] || {}),
    ...Object.fromEntries(Object.entries(values).filter(([id]) => allowed.has(id))),
  };
  methods.persistModelSelection?.();
}

export function restoreCurrentModelParameterDraft(): void {
  const { state, els, methods } = getLegacyBridge();
  const modelId = state.selectedModelId || "";
  const model = state.generationCatalog?.models.find((item) => item.id === modelId);
  if (!model) return;
  if (!isGptImageModelId(model.id)) {
    renderCurrentModelParameters();
    return;
  }
  renderCurrentModelParameters();
  const draft = {
    ...Object.fromEntries(model.parameters.map((parameter) => [parameter.id, parameter.default])),
    ...(state.parameterDraftsByModel[modelId] || {}),
  };
  if (typeof draft["canvas.resolution"] === "string" && els.resolution) els.resolution.value = draft["canvas.resolution"];
  if (typeof draft["canvas.aspect_ratio"] === "string" && els.ratio) els.ratio.value = draft["canvas.aspect_ratio"];
  if ((draft["canvas.resolution"] || draft["canvas.aspect_ratio"]) && typeof methods.updateSizeFromPreset === "function") {
    methods.updateSizeFromPreset();
  }
  if (typeof draft["canvas.size"] === "string") methods.syncSizeControlsFromSize?.(draft["canvas.size"]);
  if (typeof draft["gpt.quality"] === "string" && els.quality) els.quality.value = draft["gpt.quality"];
  if (typeof draft["output.format"] === "string" && els.outputFormat) els.outputFormat.value = draft["output.format"];
  if (typeof draft["gpt.moderation"] === "string" && els.moderation) els.moderation.value = draft["gpt.moderation"];
  if (typeof draft["gpt.output_compression"] === "number" && els.compression) els.compression.value = String(draft["gpt.output_compression"]);
  if (typeof draft["gpt.web_search"] === "boolean" && els.webSearch) {
    els.webSearch.checked = draft["gpt.web_search"] && (selectedProviderBinding()?.protocol_profile || "").endsWith("_responses");
  }
  if (typeof draft["output.count"] === "number" && els.nInput) els.nInput.value = String(draft["output.count"]);
  methods.syncRadioButtons?.(els.quality, els.outputFormat, els.moderation);
  methods.updateQuantity?.();
  methods.updateCompression?.();
  renderCurrentModelParameters();
}

export function initModelParameterDraftFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    restoreCurrentModelParameterDraft,
    saveCurrentModelParameterDraft,
  });
}
