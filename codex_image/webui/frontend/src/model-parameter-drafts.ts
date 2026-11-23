import type { CatalogModel, CatalogParameterDefinition } from "./types";
import { getLegacyBridge } from "./state";
import { renderCurrentModelParameters } from "./model-parameters";

function cloneValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneValue(item)]));
  }
  return value;
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
    if (sourceIds.has(definition.id)) {
      const sourceValue = sourceDraft[definition.id];
      return [definition.id, cloneValue(
        parameterValueValid(definition, sourceValue) ? sourceValue : definition.default,
      )];
    }
    const targetValue = targetDraft[definition.id];
    return [definition.id, cloneValue(
      parameterValueValid(definition, targetValue) ? targetValue : definition.default,
    )];
  }));
}

// Controls write straight into the draft, so saving only persists it.
export function saveCurrentModelParameterDraft(): void {
  getLegacyBridge().methods.persistModelSelection?.();
}

export function restoreCurrentModelParameterDraft(): void {
  renderCurrentModelParameters();
}

export function initModelParameterDraftFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    restoreCurrentModelParameterDraft,
    saveCurrentModelParameterDraft,
  });
}
