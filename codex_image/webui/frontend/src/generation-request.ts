import { canonicalControlValues } from "./model-parameter-drafts";
import { activeParameterValuesFor } from "./model-parameters";
import { selectedProviderBinding } from "./provider-selection";
import { getLegacyBridge } from "./state";
import { isGptImageModelId } from "./model-identifiers";

export interface CanonicalGenerationSelection {
  canonicalModelId: string;
  providerId: string;
  bindingId: string;
  parameters: Record<string, unknown>;
}

function sortedRecord(values: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.keys(values).sort().map((key) => [key, values[key]]));
}

export function currentGenerationSelection(): CanonicalGenerationSelection {
  const { state, methods } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
  if (!model || !state.selectedProviderId) {
    return { canonicalModelId: "", providerId: "", bindingId: "", parameters: {} };
  }
  let draft = state.parameterDraftsByModel[model.id] || {};
  if (isGptImageModelId(model.id) && typeof methods.currentTaskParams === "function") {
    const currentValues = canonicalControlValues(
      methods.currentTaskParams(),
      selectedProviderBinding()?.protocol_profile || "",
    );
    draft = { ...draft, ...currentValues };
    // Loading a completed task intentionally updates the visible legacy
    // controls. Do not persist those historical values as the model draft
    // while the task handoff is in progress.
    if (!state.applyingCompletedTaskOutputSettings) {
      state.parameterDraftsByModel[model.id] = draft;
    }
  }
  return {
    canonicalModelId: model.id,
    providerId: state.selectedProviderId,
    bindingId: selectedProviderBinding()?.id || "",
    parameters: activeParameterValuesFor(model, state.mode, draft),
  };
}

export function appendCanonicalGenerationFields(
  form: FormData,
  selection: CanonicalGenerationSelection,
): void {
  form.append("canonical_model_id", selection.canonicalModelId);
  form.append("provider_id", selection.providerId);
  form.append("binding_id", selection.bindingId);
  form.append("parameters_json", JSON.stringify(sortedRecord(selection.parameters)));
}
