import type {
  CatalogModel,
  CatalogParameterDefinition,
  CatalogParameterVisibility,
  CatalogSizeSpec,
  GenerationCatalog,
} from "./types";

/** Attach each family's earlier parameter names to its models, for upgrading stored values. */
export function attachParameterRenames<T>(payload: T): T {
  if (!payload || typeof payload !== "object") return payload;
  const catalog = payload as unknown as Partial<GenerationCatalog>;
  if (!Array.isArray(catalog.models)) return payload;
  const renames = catalog.parameter_renames || {};
  return {
    ...catalog,
    models: catalog.models.map((model) => ({
      ...model,
      parameter_renames: { ...(renames[model?.family_id] || {}) },
    })),
  } as unknown as T;
}

export function usesUnifiedParameters(model: Pick<CatalogModel, "parameters">): boolean {
  return model.parameters.some((definition) => definition.id === "canvas.mode");
}

function presetForSize(spec: CatalogSizeSpec, size: string): [string, string] | null {
  for (const [resolution, ratios] of Object.entries(spec.presets)) {
    for (const [ratio, [width, height]] of Object.entries(ratios)) {
      if (`${width}x${height}` === size) return [ratio, resolution];
    }
  }
  return null;
}

/**
 * Rewrite earlier parameter names into the unified vocabulary. Mirrors the
 * backend's upgrade_parameters and is idempotent, so it is safe on drafts,
 * locks and history that may already use the unified names.
 */
export function upgradeParameters(
  model: CatalogModel,
  parameters: Record<string, unknown>,
): Record<string, unknown> {
  if (!usesUnifiedParameters(model)) return { ...parameters };
  const upgraded = { ...parameters };
  const defined = new Set(model.parameters.map((definition) => definition.id));
  for (const [previous, current] of Object.entries(model.parameter_renames || {})) {
    if (previous in upgraded && defined.has(current) && !(current in upgraded)) {
      upgraded[current] = upgraded[previous];
      delete upgraded[previous];
    }
  }
  const spec = model.size_spec;
  if (spec && Object.keys(spec.presets).length && !("canvas.mode" in upgraded) && "canvas.size" in upgraded) {
    const size = upgraded["canvas.size"];
    delete upgraded["canvas.size"];
    const text = typeof size === "string" ? size.trim() : "";
    const preset = text ? presetForSize(spec, text) : null;
    if (text === "auto") {
      upgraded["canvas.mode"] = "auto";
    } else if (preset) {
      upgraded["canvas.mode"] = "preset";
      upgraded["canvas.aspect_ratio"] = preset[0];
      upgraded["canvas.resolution"] = preset[1];
    } else {
      upgraded["canvas.mode"] = "custom";
      upgraded["canvas.size"] = size;
    }
  }
  return upgraded;
}

function conditionHolds(
  condition: CatalogParameterVisibility,
  values: Record<string, unknown>,
  definitions: Map<string, CatalogParameterDefinition>,
): boolean {
  const actual = condition.parameter_id in values
    ? values[condition.parameter_id]
    : definitions.get(condition.parameter_id)?.default;
  if (condition.operator === "equals") return actual === condition.value;
  if (condition.operator === "not_equals") return actual !== condition.value;
  return Array.isArray(condition.value) && condition.value.includes(actual);
}

/** The reason a value is not allowed with the other current values, or "" when it is. */
export function valueRequirementReason(
  model: CatalogModel,
  definition: CatalogParameterDefinition,
  value: unknown,
  values: Record<string, unknown>,
): string {
  const definitions = new Map(model.parameters.map((item) => [item.id, item]));
  const failed = (definition.value_requirements || []).find((requirement) => (
    requirement.value === value && !conditionHolds(requirement.condition, values, definitions)
  ));
  return failed ? failed.reason : "";
}
