import { activeParameterValuesFor, selectedBindingParameterIds } from "./model-parameters";
import { selectedProviderBinding } from "./provider-selection";
import { getLegacyBridge } from "./state";

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
  const { state } = getLegacyBridge();
  const model = state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
  if (!model || !state.selectedProviderId) {
    return { canonicalModelId: "", providerId: "", bindingId: "", parameters: {} };
  }
  const draft = state.parameterDraftsByModel[model.id] || {};
  return {
    canonicalModelId: model.id,
    providerId: state.selectedProviderId,
    bindingId: selectedProviderBinding()?.id || "",
    parameters: activeParameterValuesFor(model, state.mode, draft, selectedBindingParameterIds(model.id)),
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
