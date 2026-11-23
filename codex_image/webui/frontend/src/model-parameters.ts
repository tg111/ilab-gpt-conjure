import { createPixelSizeEditor, customSizeError, gifFrameLimit, refreshFirstImageButtons } from "./image-size-editor";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { aspectRatioSlots, createAspectRatioIcon } from "./aspect-ratio-controls";
import { refreshSegmentedIndicators } from "./segmented-indicator";
import { MOBILE_WORKSPACE_QUERY } from "./mobile-shell";
import { resolveModeSettingsVisibility } from "./mode-settings-visibility";
import { getLegacyBridge } from "./state";
import { upgradeParameters, valueRequirementReason } from "./unified-parameters";
import type {
  CatalogModel,
  CatalogObjectPreset,
  CatalogParameterDefinition,
  CatalogProviderBinding,
  GenerationOperation,
  ParameterMigrationReport,
} from "./types";

interface RenderContext {
  readOnly: boolean;
  model: CatalogModel;
  values: Record<string, unknown>;
  root: HTMLElement;
}

type ParameterRenderer = (
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
) => HTMLElement;

function cloneValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, cloneValue(item)]));
  }
  return value;
}

export function parameterValueValid(definition: CatalogParameterDefinition, value: unknown): boolean {
  const typeValid = definition.value_type === "string" ? typeof value === "string"
    : definition.value_type === "integer" ? typeof value === "number" && Number.isInteger(value)
      : definition.value_type === "boolean" ? typeof value === "boolean"
        : definition.value_type === "object" ? Boolean(value) && typeof value === "object" && !Array.isArray(value)
          : false;
  if (!typeValid) return false;
  if (definition.object_choices?.length && value && typeof value === "object" && !Array.isArray(value)) {
    const choices = new Map(definition.object_choices.map((row) => [row.key, row]));
    for (const [key, item] of Object.entries(value)) {
      const row = choices.get(key);
      if (row && (typeof item !== "string" || !row.allowed_values.includes(item))) return false;
    }
  }
  if (definition.allowed_values.length && !definition.allowed_values.includes(value)) return false;
  if (typeof value === "number") {
    if (definition.minimum !== null && value < definition.minimum) return false;
    if (definition.maximum !== null && value > definition.maximum) return false;
    if (definition.step !== null) {
      const base = definition.minimum ?? 0;
      const quotient = (value - base) / definition.step;
      if (Math.abs(quotient - Math.round(quotient)) > 1e-9) return false;
    }
  }
  return true;
}

function modelParameterValueValid(model: CatalogModel, definition: CatalogParameterDefinition, value: unknown, values: Record<string, unknown>): boolean {
  if (definition.control === "pixel_size" && model.size_spec?.custom) {
    const outputFormat = values["output.format"] ?? model.parameters.find((item) => item.id === "output.format")?.default;
    return !customSizeError(model.size_spec.custom, value, outputFormat);
  }
  return parameterValueValid(definition, value) && !valueRequirementReason(model, definition, value, values);
}

// Readable explanations for value requirements reported by the catalog.
const VALUE_REQUIREMENT_LABEL_KEYS: Readonly<Record<string, string>> = {
  transparent_background_requires_png_webp_or_svg: "output.transparencyFormat",
};

function segmentLabel(definition: CatalogParameterDefinition, value: unknown): string {
  const key = definition.value_label_keys?.[definition.allowed_values.indexOf(value)];
  return key ? translate(key) : String(value);
}

export function nextObjectChoiceValue(
  definition: Pick<CatalogParameterDefinition, "object_choices">,
  value: Record<string, unknown>,
  key: string,
  next: string,
): Record<string, unknown> {
  const row = definition.object_choices?.find((item) => item.key === key);
  if (!row || !row.allowed_values.includes(next)) return { ...value };
  const updated = { ...value };
  if (next === row.default) delete updated[key];
  else updated[key] = next;
  return updated;
}

function managedPresetKeys(definition: Pick<CatalogParameterDefinition, "object_presets">): Set<string> {
  return new Set(definition.object_presets?.flatMap((preset) => Object.keys(preset.value)) || []);
}

export function matchingObjectPreset(
  definition: Pick<CatalogParameterDefinition, "object_presets">,
  value: Record<string, unknown>,
): CatalogObjectPreset | null {
  const presets = definition.object_presets || [];
  const managedKeys = managedPresetKeys(definition);
  const presentManagedKeys = [...managedKeys].filter((key) => key in value);
  if (presentManagedKeys.length === 0) {
    return presets.find((preset) => preset.matches_empty) || null;
  }
  return presets.find((preset) => (
    [...managedKeys].every((key) => key in value && key in preset.value && value[key] === preset.value[key])
  )) || null;
}

export function nextObjectPresetValue(
  definition: Pick<CatalogParameterDefinition, "object_presets">,
  value: Record<string, unknown>,
  preset: CatalogObjectPreset,
): Record<string, unknown> {
  if (!definition.object_presets?.some((item) => item.id === preset.id)) return { ...value };
  const updated = { ...value };
  managedPresetKeys(definition).forEach((key) => delete updated[key]);
  Object.assign(updated, cloneValue(preset.value));
  return updated;
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

export function initializeParameterDraft(
  model: CatalogModel,
  stored: Record<string, unknown> = {},
): ParameterMigrationReport {
  // Drafts, locks and history may use earlier parameter names.
  const previous = upgradeParameters(model, stored);
  const values: Record<string, unknown> = {};
  const defaulted: ParameterMigrationReport["defaulted"] = [];
  const definitions = new Map(model.parameters.map((definition) => [definition.id, definition]));
  for (const definition of model.parameters) {
    if (!(definition.id in previous)) {
      values[definition.id] = cloneValue(definition.default);
      continue;
    }
    const prior = previous[definition.id];
    if (modelParameterValueValid(model, definition, prior, previous)) {
      values[definition.id] = cloneValue(prior);
    } else {
      const replacement = cloneValue(definition.default);
      values[definition.id] = replacement;
      defaulted.push({ id: definition.id, previous: cloneValue(prior), replacement: cloneValue(replacement) });
    }
  }
  const dropped = Object.entries(previous)
    .filter(([id]) => !definitions.has(id))
    .map(([id, prior]) => ({ id, previous: cloneValue(prior) }));
  return { values, defaulted, dropped };
}

export function migrateParameterValues(
  model: CatalogModel,
  previous: Record<string, unknown>,
): ParameterMigrationReport {
  return initializeParameterDraft(model, previous);
}

export function parameterAffectsVisibility(model: CatalogModel, parameterId: string): boolean {
  return model.parameters.some((definition) => definition.visible_when.some(
    (condition) => condition.parameter_id === parameterId,
  ));
}

/**
 * Parameter ids the selected provider binding can act on, or null when the
 * catalog does not say (every model parameter is then offered).
 */
function selectedBinding(modelId: string): CatalogProviderBinding | null {
  const { state } = getLegacyBridge();
  const binding = state.generationCatalog?.providers
    .find((provider) => provider.id === state.selectedProviderId)?.bindings
    .find((item) => item.id === state.selectedProviderBindingId);
  return binding?.canonical_model_id === modelId ? binding : null;
}

export function selectedBindingParameterIds(modelId: string): ReadonlySet<string> | null {
  const binding = selectedBinding(modelId);
  if (!binding?.capabilities) return null;
  return new Set(binding.capabilities.parameter_ids);
}

export function activeParameterValuesFor(
  model: CatalogModel,
  operation: GenerationOperation,
  draft: Record<string, unknown>,
  supported: ReadonlySet<string> | null = null,
): Record<string, unknown> {
  const values = Object.fromEntries(model.parameters.map((definition) => {
    const value = draft[definition.id];
    return [definition.id, cloneValue(modelParameterValueValid(model, definition, value, draft) ? value : definition.default)];
  }));
  return Object.fromEntries(model.parameters
    .filter((definition) => definition.operations.includes(operation))
    .filter((definition) => definition.control !== "notice")
    .filter((definition) => !supported || supported.has(definition.id))
    .filter((definition) => definition.visible_when.every((condition) => conditionMatches(condition, values)))
    .map((definition) => [definition.id, cloneValue(values[definition.id])]));
}

export function activeParameterValues(model: CatalogModel): Record<string, unknown> {
  const { state } = getLegacyBridge();
  return activeParameterValuesFor(
    model,
    state.mode as GenerationOperation,
    state.parameterDraftsByModel[model.id] || {},
    selectedBindingParameterIds(model.id),
  );
}

function fieldShell(definition: CatalogParameterDefinition): HTMLDivElement {
  const field = document.createElement("div");
  field.className = `field model-parameter-field${definition.full_width ? " full-width" : ""}`;
  field.dataset.parameterId = definition.id;
  field.dataset.parameterGroup = definition.group;
  const label = document.createElement("span");
  label.className = "model-parameter-label";
  label.textContent = translate(definition.label_key);
  label.classList.toggle("output-label-pair", /^\p{Script=Han}{2}$/u.test(label.textContent));
  // Four Han characters stack as two pairs beside the control.
  label.classList.toggle("output-label-quad", /^\p{Script=Han}{4}$/u.test(label.textContent));
  field.append(label);
  return field;
}

function setReadOnly(control: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement, readOnly: boolean): void {
  if (!readOnly) return;
  control.disabled = true;
  control.tabIndex = -1;
  control.setAttribute("aria-readonly", "true");
}

function interactiveModel(context: RenderContext): CatalogModel {
  if (context.readOnly) return context.model;
  const { state } = getLegacyBridge();
  return state.generationCatalog?.models.find((model) => model.id === state.selectedModelId) || context.model;
}

function commitValue(context: RenderContext, definition: CatalogParameterDefinition, value: unknown, rerender = false): void {
  if (context.readOnly) return;
  const model = interactiveModel(context);
  const currentDefinition = model.parameters.find((item) => item.id === definition.id);
  if (!currentDefinition) return;
  setParameterValue(model.id, currentDefinition.id, value);
  // Typing pixels must not re-render, which would replace the inputs being edited;
  // limits that depend on the new value are refreshed in place.
  if (rerender) renderModelParameters(model, { readOnly: false });
  else refreshDynamicLimits();
}

function renderSelect(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const select = document.createElement("select");
  select.className = "control";
  select.setAttribute("aria-label", translate(definition.label_key));
  definition.allowed_values.forEach((allowed) => {
    const option = document.createElement("option");
    option.value = String(allowed);
    option.textContent = String(allowed);
    select.append(option);
  });
  select.value = String(value);
  setReadOnly(select, context.readOnly);
  select.addEventListener("change", () => commitValue(
    context,
    definition,
    select.value,
    parameterAffectsVisibility(interactiveModel(context), definition.id),
  ));
  field.append(select);
  return field;
}

function renderSegmented(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  if (definition.allowed_values.length === 1) {
    const staticValue = document.createElement("div");
    staticValue.className = "control model-parameter-static-value";
    staticValue.textContent = String(definition.allowed_values[0]);
    staticValue.setAttribute("aria-label", translate(definition.label_key));
    field.append(staticValue);
    return field;
  }
  const group = document.createElement("div");
  const multiline = definition.allowed_values.length > 4;
  group.className = `radio-group model-parameter-segmented${multiline ? " model-parameter-segmented-multiline" : ""}`;
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  definition.allowed_values.forEach((allowed) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `radio-btn${allowed === value ? " active" : ""}`;
    button.dataset.val = String(allowed);
    button.textContent = segmentLabel(definition, allowed);
    const blockedReason = allowed === value ? "" : valueRequirementReason(context.model, definition, allowed, context.values);
    if (blockedReason) button.title = translate(VALUE_REQUIREMENT_LABEL_KEYS[blockedReason] || blockedReason);
    button.disabled = context.readOnly || Boolean(blockedReason);
    button.tabIndex = context.readOnly ? -1 : 0;
    button.setAttribute("aria-pressed", allowed === value ? "true" : "false");
    button.addEventListener("click", () => {
      if (context.readOnly || button.classList.contains("active")) return;
      group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", active ? "true" : "false");
      });
      commitValue(
        context,
        definition,
        allowed,
        parameterAffectsVisibility(interactiveModel(context), definition.id),
      );
      refreshSegmentedIndicators();
    });
    group.append(button);
  });
  field.append(group);
  return field;
}

function renderBooleanSegmented(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const group = document.createElement("div");
  group.className = "radio-group model-parameter-segmented model-parameter-boolean-segmented";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  const choices = [
    { value: false, label: translate("output.lock.disabled") },
    { value: true, label: translate("output.lock.enabled") },
  ];
  choices.forEach((choice) => {
    const button = document.createElement("button");
    const active = choice.value === Boolean(value);
    button.type = "button";
    button.className = `radio-btn${active ? " active" : ""}`;
    button.textContent = choice.label;
    button.disabled = context.readOnly;
    button.tabIndex = context.readOnly ? -1 : 0;
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.addEventListener("click", () => {
      if (context.readOnly || button.classList.contains("active")) return;
      group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
        const isActive = item === button;
        item.classList.toggle("active", isActive);
        item.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
      commitValue(
        context,
        definition,
        choice.value,
        parameterAffectsVisibility(interactiveModel(context), definition.id),
      );
      refreshSegmentedIndicators();
    });
    group.append(button);
  });
  field.append(group);
  return field;
}

function renderToggle(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const label = document.createElement("label");
  label.className = "web-search-toggle model-parameter-toggle";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = Boolean(value);
  input.setAttribute("aria-label", translate(definition.label_key));
  setReadOnly(input, context.readOnly);
  const track = document.createElement("span");
  track.className = "web-search-toggle-track";
  track.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.className = "web-search-toggle-text";
  text.textContent = translate(input.checked ? "output.lock.enabled" : "output.lock.disabled");
  input.addEventListener("change", () => {
    text.textContent = translate(input.checked ? "output.lock.enabled" : "output.lock.disabled");
    commitValue(
      context,
      definition,
      input.checked,
      parameterAffectsVisibility(interactiveModel(context), definition.id),
    );
  });
  label.append(input, track, text);
  field.append(label);
  return field;
}

function renderNumeric(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
  slider: boolean,
): HTMLElement {
  const field = fieldShell(definition);
  const input = document.createElement("input");
  input.className = slider ? "slider" : "control";
  input.type = slider ? "range" : "number";
  input.value = String(value);
  input.setAttribute("aria-label", translate(definition.label_key));
  if (definition.minimum !== null) input.min = String(definition.minimum);
  if (definition.maximum !== null) input.max = String(definition.maximum);
  if (definition.step !== null) input.step = String(definition.step);
  setReadOnly(input, context.readOnly);
  const output = document.createElement("output");
  output.className = "model-parameter-number-value";
  output.textContent = String(value);
  const error = document.createElement("span");
  error.className = "model-parameter-error hidden";
  error.setAttribute("role", "alert");
  const validate = (next: number, commit: boolean) => {
    const limit = Number(input.dataset.limit || NaN);
    const message = !parameterValueValid(definition, next)
      ? translate("modelParameters.invalidValue")
      : next > limit ? formatTranslation("output.frameCountLimit", { max: limit }) : "";
    error.textContent = message;
    error.classList.toggle("hidden", !message);
    input.setAttribute("aria-invalid", message ? "true" : "false");
    setValidationError(interactiveModel(context).id, definition.id, message);
    if (!message && commit) commitValue(context, definition, next);
  };
  input.addEventListener("input", () => {
    output.textContent = input.value;
    validate(Number(input.value), true);
  });
  if (definition.id === GIF_FRAME_COUNT && !context.readOnly) {
    // The cap follows the canvas and supplier; keep an over-limit draft editable but blocked.
    const refresh = () => {
      const draft = getLegacyBridge().state.parameterDraftsByModel?.[context.model.id] || {};
      const limit = currentGifFrameLimit(context.model, definition, { ...context.values, ...draft });
      if (limit === null) delete input.dataset.limit;
      else input.dataset.limit = input.max = String(limit);
      validate(Number(input.value), false);
    };
    input.dataset.dynamicLimit = "gif-frames";
    (input as HTMLInputElement & { refreshLimit?: () => void }).refreshLimit = refresh;
    queueMicrotask(refresh);
  }
  if (slider) field.append(input, output, error);
  else field.append(input, error);
  return field;
}

const GIF_FRAME_COUNT = "gpt.frame_count";

function currentGifFrameLimit(
  model: CatalogModel,
  definition: CatalogParameterDefinition,
  values: Record<string, unknown>,
): number | null {
  const { state } = getLegacyBridge();
  const provider = state.generationCatalog?.providers.find((item) => item.id === state.selectedProviderId);
  const providerLimit = state.mode === "edit" ? provider?.gif_edit_max_frames ?? null : null;
  return gifFrameLimit(model, definition.maximum, values, providerLimit);
}

function usesMobileWorkspace(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(MOBILE_WORKSPACE_QUERY).matches;
}

/**
 * On desktop the collapsed advanced options open from the output header, like
 * the earlier extra-options button, so they never add a row to the form.
 * Mobile keeps them inline in the parameter sheet.
 */
function placeAdvancedOptions(root: HTMLElement, slot: HTMLElement, wasOpen: boolean): void {
  const details = root.querySelector<HTMLDetailsElement>(":scope > details.model-parameter-advanced");
  const inHeader = Boolean(details) && !usesMobileWorkspace();
  slot.replaceChildren(...(inHeader && details ? [details] : []));
  slot.classList.toggle("hidden", !inHeader);
  if (details && wasOpen) details.open = true;
}

function closeAdvancedPopover(event: Event): void {
  const details = document.querySelector<HTMLDetailsElement>("#modelAdvancedSlot > details[open]");
  if (!details) return;
  if (event instanceof KeyboardEvent) {
    if (event.key !== "Escape") return;
    details.open = false;
    details.querySelector<HTMLElement>("summary")?.focus();
    return;
  }
  if (!details.contains(event.target as Node)) details.open = false;
}

/** Re-check controls whose limits depend on other values that changed without a rerender. */
function refreshDynamicLimits(): void {
  // Only interactive controls carry the marker; they may sit in the grid or a slot.
  if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
  document.querySelectorAll<HTMLInputElement & { refreshLimit?: () => void }>("[data-dynamic-limit]")
    .forEach((input) => input.refreshLimit?.());
}

function renderSlider(definition: CatalogParameterDefinition, value: unknown, context: RenderContext): HTMLElement {
  return renderNumeric(definition, value, context, true);
}

function renderNumber(definition: CatalogParameterDefinition, value: unknown, context: RenderContext): HTMLElement {
  return renderNumeric(definition, value, context, false);
}

function renderImageSize(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = renderSegmented(definition, value, context);
  // The mode buttons name themselves; the group keeps its accessible label.
  // The resulting pixels are shown in the execution summary above the form.
  field.querySelector(".model-parameter-label")?.classList.add("sr-only");
  return field;
}

function renderPixelSize(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const rules = context.model.size_spec?.custom;
  if (!rules) return renderText(definition, value, context);
  const field = fieldShell(definition);
  field.append(createPixelSizeEditor({
    label: translate(definition.label_key),
    value,
    rules,
    outputFormat: context.values["output.format"],
    readOnly: context.readOnly,
    commit: (next) => commitValue(context, definition, next),
    reportError: (message) => {
      if (!context.readOnly) setValidationError(interactiveModel(context).id, definition.id, message);
    },
  }));
  return field;
}

function setValidationError(modelId: string, parameterId: string, message: string): void {
  const { state, els } = getLegacyBridge();
  const errors = state.parameterValidationErrorsByModel[modelId] || {};
  if (message) errors[parameterId] = message;
  else delete errors[parameterId];
  state.parameterValidationErrorsByModel[modelId] = errors;
  if (els.runButton) els.runButton.disabled = !state.authAvailable || Object.keys(errors).length > 0;
}

function renderText(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const input = definition.value_type === "object" ? document.createElement("textarea") : document.createElement("input");
  input.className = "control model-parameter-text";
  input.setAttribute("aria-label", translate(definition.label_key));
  if (input instanceof HTMLTextAreaElement) {
    input.rows = 4;
    input.value = JSON.stringify(value, null, 2);
  } else {
    input.type = "text";
    input.value = String(value);
  }
  setReadOnly(input, context.readOnly);
  const error = document.createElement("span");
  error.className = "model-parameter-error hidden";
  error.setAttribute("role", "alert");
  const handle = () => {
    if (context.readOnly) return;
    if (definition.value_type !== "object") {
      const message = parameterValueValid(definition, input.value) ? "" : translate("modelParameters.invalidValue");
      error.textContent = message;
      error.classList.toggle("hidden", !message);
      setValidationError(interactiveModel(context).id, definition.id, message);
      if (!message) commitValue(context, definition, input.value);
      return;
    }
    let parsed: unknown;
    let message = "";
    try {
      parsed = JSON.parse(input.value);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) message = translate("modelParameters.objectRequired");
    } catch {
      message = translate("modelParameters.invalidJson");
    }
    error.textContent = message;
    error.classList.toggle("hidden", !message);
    setValidationError(interactiveModel(context).id, definition.id, message);
    if (!message) commitValue(context, definition, parsed);
  };
  input.addEventListener("input", handle);
  input.addEventListener("blur", handle);
  field.append(input, error);
  return field;
}

function renderNotice(
  definition: CatalogParameterDefinition,
  value: unknown,
  _context: RenderContext,
): HTMLElement {
  const notice = document.createElement("p");
  notice.className = `model-parameter-notice${definition.full_width ? " full-width" : ""}`;
  notice.dataset.parameterId = definition.id;
  notice.textContent = String(value || translate(definition.label_key));
  return notice;
}

function renderChoiceGrid(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  field.classList.add("model-parameter-choice-grid");
  const current = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  definition.object_choices?.forEach((row) => {
    const choiceRow = document.createElement("div");
    choiceRow.className = "model-parameter-choice-row";
    const label = document.createElement("span");
    label.className = "model-parameter-choice-label";
    label.textContent = translate(row.label_key);
    const group = document.createElement("div");
    group.className = "radio-group model-parameter-choice-options model-parameter-segmented-multiline";
    group.setAttribute("role", "group");
    group.setAttribute("aria-label", translate(row.label_key));
    const selected = typeof current[row.key] === "string" ? String(current[row.key]) : row.default;
    row.allowed_values.forEach((allowed, index) => {
      const button = document.createElement("button");
      const active = selected === allowed;
      button.type = "button";
      button.className = `radio-btn${active ? " active" : ""}`;
      button.textContent = translate(row.label_keys[index] || row.label_key);
      button.title = allowed;
      button.disabled = context.readOnly;
      button.tabIndex = context.readOnly ? -1 : 0;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.addEventListener("click", () => {
        if (context.readOnly || button.classList.contains("active")) return;
        group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
          const isActive = item === button;
          item.classList.toggle("active", isActive);
          item.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
        const nextValue = nextObjectChoiceValue(definition, current, row.key, allowed);
        Object.keys(current).forEach((key) => delete current[key]);
        Object.assign(current, nextValue);
        commitValue(context, definition, nextValue);
      });
      group.append(button);
    });
    choiceRow.append(label, group);
    field.append(choiceRow);
  });
  return field;
}

function renderObjectPresets(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const group = document.createElement("div");
  group.className = "radio-group model-parameter-object-presets";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  let current = value && typeof value === "object" && !Array.isArray(value)
    ? { ...value as Record<string, unknown> }
    : {};
  const selected = matchingObjectPreset(definition, current);
  definition.object_presets?.forEach((preset) => {
    const button = document.createElement("button");
    const active = selected?.id === preset.id;
    button.type = "button";
    button.className = `radio-btn${active ? " active" : ""}`;
    button.textContent = translate(preset.label_key);
    button.disabled = context.readOnly;
    button.tabIndex = context.readOnly ? -1 : 0;
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.addEventListener("click", () => {
      if (context.readOnly || button.classList.contains("active")) return;
      group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
        const isActive = item === button;
        item.classList.toggle("active", isActive);
        item.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
      current = nextObjectPresetValue(definition, current, preset);
      commitValue(context, definition, current);
      refreshSegmentedIndicators();
    });
    group.append(button);
  });
  field.append(group);
  return field;
}

function renderAspectRatioGrid(
  definition: CatalogParameterDefinition,
  value: unknown,
  context: RenderContext,
): HTMLElement {
  const field = fieldShell(definition);
  const group = document.createElement("div");
  group.className = "radio-group model-aspect-ratio-grid";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", translate(definition.label_key));
  aspectRatioSlots(definition.allowed_values.map(String)).forEach((ratioSlot) => {
    const slot = document.createElement("div");
    slot.className = "aspect-ratio-slot";
    ratioSlot.values.forEach((allowed) => {
      const button = document.createElement("button");
      const active = allowed === value;
      button.type = "button";
      button.className = `radio-btn${active ? " active" : ""}`;
      button.dataset.val = allowed;
      button.disabled = context.readOnly;
      button.tabIndex = context.readOnly ? -1 : 0;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      const icon = createAspectRatioIcon(allowed);
      const label = document.createElement("span");
      label.className = "aspect-ratio-label";
      label.textContent = allowed;
      if (icon) button.append(icon, label);
      else {
        button.classList.add("aspect-ratio-no-icon");
        button.append(label);
      }
      button.addEventListener("click", () => {
        if (context.readOnly || button.classList.contains("active")) return;
        group.querySelectorAll<HTMLButtonElement>(".radio-btn").forEach((item) => {
          const isActive = item === button;
          item.classList.toggle("active", isActive);
          item.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
        commitValue(context, definition, allowed);
      });
      slot.append(button);
    });
    group.append(slot);
  });
  field.append(group);
  return field;
}

export const PARAMETER_RENDERERS: Record<CatalogParameterDefinition["control"], ParameterRenderer> = {
  select: renderSelect,
  segmented: renderSegmented,
  boolean_segmented: renderBooleanSegmented,
  toggle: renderToggle,
  slider: renderSlider,
  number: renderNumber,
  text: renderText,
  notice: renderNotice,
  choice_grid: renderChoiceGrid,
  object_presets: renderObjectPresets,
  aspect_ratio_grid: renderAspectRatioGrid,
  image_size: renderImageSize,
  pixel_size: renderPixelSize,
};

// A size control with a single mode (provider-sized models) has nothing to choose.
function parameterHasChoice(definition: CatalogParameterDefinition): boolean {
  return definition.control !== "image_size" || definition.allowed_values.length > 1;
}

export function advancedParametersAreExpanded(model: CatalogModel, readOnly: boolean): boolean {
  return readOnly || model.expand_advanced_parameters === true;
}

function parameterTranslations(definition: CatalogParameterDefinition): string[] {
  return [
    translate(definition.label_key),
    ...(definition.object_choices || []).flatMap((choice) => [
      translate(choice.label_key),
      ...choice.label_keys.map((key) => translate(key)),
    ]),
    ...(definition.object_presets || []).map((preset) => translate(preset.label_key)),
  ];
}

// Other values a field's rendering reads besides its own.
const FINGERPRINT_DEPENDENCIES: Readonly<Partial<Record<CatalogParameterDefinition["control"], string[]>>> = {
  pixel_size: ["output.format"],
};

export function parameterRenderFingerprint(
  definition: CatalogParameterDefinition,
  value: unknown,
  readOnly: boolean,
  values: Record<string, unknown> = {},
): string {
  const dependencies = [
    ...(FINGERPRINT_DEPENDENCIES[definition.control] || []),
    ...(definition.value_requirements || []).map((requirement) => requirement.condition.parameter_id),
  ].map((id) => values[id]);
  return JSON.stringify([definition, value, readOnly, parameterTranslations(definition), dependencies]);
}

function resolvedParameterValues(
  model: CatalogModel,
  values: Record<string, unknown>,
): Record<string, unknown> {
  return Object.fromEntries(model.parameters.map((definition) => [
    definition.id,
    modelParameterValueValid(model, definition, values[definition.id], values) ? values[definition.id] : cloneValue(definition.default),
  ]));
}

function visibleParameterDefinitions(
  model: CatalogModel,
  values: Record<string, unknown>,
  operation: GenerationOperation,
  supported: ReadonlySet<string> | null = null,
): CatalogParameterDefinition[] {
  return model.parameters
    .filter((definition) => definition.operations.includes(operation))
    .filter((definition) => !supported || supported.has(definition.id))
    .filter(parameterHasChoice)
    .filter((definition) => definition.visible_when.every((condition) => conditionMatches(condition, values)));
}

export function renderParameterDefinitionsInto(
  root: HTMLElement,
  model: CatalogModel,
  values: Record<string, unknown>,
  options: { readOnly: boolean; operation?: GenerationOperation; supported?: ReadonlySet<string> | null },
): void {
  const operation = options.operation || "generate";
  const resolvedValues = resolvedParameterValues(model, values);
  root.replaceChildren();
  const context: RenderContext = { readOnly: options.readOnly, model, values: resolvedValues, root };
  const visibleDefinitions = visibleParameterDefinitions(model, resolvedValues, operation, options.supported || null);
  visibleDefinitions
    .filter((definition) => definition.group !== "advanced")
    .forEach((definition) => root.append(PARAMETER_RENDERERS[definition.control](definition, resolvedValues[definition.id], context)));
  const advancedDefinitions = visibleDefinitions.filter((definition) => definition.group === "advanced");
  if (advancedDefinitions.length) {
    const content = document.createElement("div");
    content.className = "model-parameter-advanced-grid";
    advancedDefinitions.forEach((definition) => content.append(
      PARAMETER_RENDERERS[definition.control](definition, resolvedValues[definition.id], context),
    ));
    if (advancedParametersAreExpanded(model, options.readOnly)) {
      content.classList.add("model-parameter-advanced-grid-expanded", "full-width");
      root.append(content);
    } else {
      const details = document.createElement("details");
      details.className = "model-parameter-advanced full-width";
      const summary = document.createElement("summary");
      summary.textContent = translate("apiSettings.advancedSettings");
      details.append(summary, content);
      root.append(details);
    }
  }
  refreshSegmentedIndicators();
}

export function renderInteractiveParameterDefinitionsInto(
  root: HTMLElement,
  model: CatalogModel,
  values: Record<string, unknown>,
  operation: GenerationOperation,
): void {
  const resolvedValues = resolvedParameterValues(model, values);
  const supported = selectedBindingParameterIds(model.id);
  const visibleDefinitions = visibleParameterDefinitions(model, resolvedValues, operation, supported);
  if (visibleDefinitions.some((definition) => definition.group === "advanced")) {
    renderParameterDefinitionsInto(root, model, values, { readOnly: false, operation, supported });
    return;
  }
  const context: RenderContext = { readOnly: false, model, values: resolvedValues, root };
  const existingFields = new Map(Array.from(root.children).flatMap((child) => {
    const parameterId = (child as HTMLElement).dataset.parameterId;
    return parameterId ? [[parameterId, child as HTMLElement]] : [];
  }));
  const fields = visibleDefinitions.map((definition) => {
    const fingerprint = parameterRenderFingerprint(definition, resolvedValues[definition.id], false, resolvedValues);
    const existingField = existingFields.get(definition.id);
    if (existingField?.dataset.renderFingerprint === fingerprint) return existingField;
    const field = PARAMETER_RENDERERS[definition.control](definition, resolvedValues[definition.id], context);
    field.dataset.renderFingerprint = fingerprint;
    return field;
  });
  root.replaceChildren(...fields);
  refreshSegmentedIndicators();
}

function ensureModelDraft(model: CatalogModel): ParameterMigrationReport {
  const { state } = getLegacyBridge();
  const previous = state.parameterDraftsByModel[model.id] || {};
  const report = initializeParameterDraft(model, previous);
  state.parameterDraftsByModel[model.id] = report.values;
  state.parameterDraftVersionsByModel[model.id] = model.version;
  return report;
}

export function renderModelParameters(
  model: CatalogModel,
  options: { readOnly: boolean; root?: HTMLElement; values?: Record<string, unknown> } = { readOnly: false },
): void {
  const { state, els } = getLegacyBridge();
  const root = options.root || els.modelParameterGrid as HTMLElement | null;
  if (!root) return;
  if (options.readOnly) {
    renderParameterDefinitionsInto(root, model, options.values || {}, { readOnly: true, operation: state.mode as GenerationOperation });
    return;
  }
  ensureModelDraft(model);
  const draft = state.parameterDraftsByModel[model.id] || {};
  // A hidden field cannot be corrected, so its error must not block submission.
  const visible = new Set(visibleParameterDefinitions(
    model, resolvedParameterValues(model, draft), state.mode as GenerationOperation,
    selectedBindingParameterIds(model.id),
  ).map((definition) => definition.id));
  const errors = state.parameterValidationErrorsByModel[model.id] || {};
  Object.keys(errors).filter((id) => !visible.has(id)).forEach((id) => setValidationError(model.id, id, ""));
  root.classList.remove("hidden");
  // Tool fields render with the rest so unchanged controls are reused, then
  // move beside the main model when the selected binding shows one.
  const toolSlot = els.modelToolSlot as HTMLElement | null;
  if (toolSlot) root.append(...Array.from(toolSlot.children));
  const advancedSlot = els.modelAdvancedSlot as HTMLElement | null;
  const advancedWasOpen = Boolean(advancedSlot?.querySelector<HTMLDetailsElement>("details")?.open);
  renderInteractiveParameterDefinitionsInto(root, model, draft, state.mode as GenerationOperation);
  if (advancedSlot) placeAdvancedOptions(root, advancedSlot, advancedWasOpen);
  if (toolSlot) {
    const binding = selectedBinding(model.id);
    const besideMainModel = Boolean(binding && resolveModeSettingsVisibility(binding, false).showMainModel);
    toolSlot.replaceChildren(...(besideMainModel
      ? Array.from(root.querySelectorAll<HTMLElement>(':scope > [data-parameter-group="tools"]'))
      : []));
    toolSlot.classList.toggle("hidden", !toolSlot.children.length);
  }
  // Reused controls keep their element; their limits may depend on what changed.
  refreshDynamicLimits();
}

export function setParameterValue(modelId: string, parameterId: string, value: unknown): void {
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === modelId);
  const definition = model?.parameters.find((item) => item.id === parameterId);
  if (!model || !definition || !modelParameterValueValid(model, definition, value, state.parameterDraftsByModel[modelId] || {})) return;
  state.parameterDraftsByModel[modelId] = {
    ...(state.parameterDraftsByModel[modelId] || {}),
    [parameterId]: cloneValue(value),
  };
  if (definition.scope === "application") {
    state.generationCatalog?.models.forEach((item) => {
      if (item.parameters.some((parameter) => parameter.id === parameterId)) {
        state.parameterDraftsByModel[item.id] = {
          ...(state.parameterDraftsByModel[item.id] || {}),
          [parameterId]: cloneValue(value),
        };
      }
    });
  }
  getLegacyBridge().methods.persistModelSelection?.();
  getLegacyBridge().methods.updateRequestPreview?.();
}

/** Return the selected model's parameters to their defaults (used by "new task"). */
export function resetCurrentModelParameters(): void {
  const { state } = getLegacyBridge();
  if (!state.selectedModelId) return;
  state.parameterDraftsByModel[state.selectedModelId] = {};
  getLegacyBridge().methods.persistModelSelection?.();
  renderCurrentModelParameters();
}

export function renderCurrentModelParameters(): void {
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
  if (model) renderModelParameters(model, { readOnly: false });
}

export function initModelParametersFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    activeParameterValues,
    refreshFirstImageButtons,
    renderCurrentModelParameters,
    renderModelParameters,
    resetCurrentModelParameters,
    setParameterValue,
  });
  document.addEventListener(LOCALE_CHANGE_EVENT, renderCurrentModelParameters);
  document.addEventListener("pointerdown", closeAdvancedPopover);
  document.addEventListener("keydown", closeAdvancedPopover);
  if (typeof window.matchMedia === "function") {
    window.matchMedia(MOBILE_WORKSPACE_QUERY).addEventListener?.("change", renderCurrentModelParameters);
  }
}
