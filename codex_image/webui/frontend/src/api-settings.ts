import { getLegacyBridge } from "./state";
import { LOCALE_CHANGE_EVENT } from "./i18n";
import {
  applyAuthSourceSelection,
  authSourceDetailText,
  currentAuthSource,
  handleAuthSourceClick,
  refreshHealth,
  renderAuthSource,
  setAuthSource,
  sourceLabel,
} from "./auth-source";
import {
  setModeSettingsVariant,
  setModeSpecificElementVisibility,
  updateModeSpecificSettings,
} from "./api-mode-settings";
import {
  activeApiProvider,
  addProviderBinding,
  addApiProvider,
  apiModeLabel,
  closeApiSettingsModal,
  codexModeLabel,
  currentApiImageModel,
  currentApiMode,
  currentApiProviderId,
  currentApiProviderLabel,
  currentCodexMode,
  confirmDeleteApiProvider,
  copyApiProvider,
  deleteApiProvider,
  editApiProvider,
  hideApiKeyReveal,
  handleProviderBindingEditorChange,
  mergeApiProviderKeys,
  normalizeApiProvider,
  openGenerationProviderSettings,
  openApiSettingsModal,
  persistApiSettings,
  populateApiSettingsForm,
  enteredApiKey,
  toggleApiKeyReveal,
  renderApiProviderList,
  refreshApiSettings,
  restoreApiSettings,
  cancelApiProviderEdit,
  saveApiProviderEdit,
  selectApiProvider,
  selectCodexMode,
  setApiKeyRevealVisible,
  setApiSettingsFeedback,
  syncSvgAuthorModelVisibility,
  taskApiProviderId,
  taskApiProviderLabel,
  taskBackendLabel,
  taskBackendValue,
  reorderApiProviders,
  removeProviderBinding,
  toggleApiProviderSortMode,
  addDiscoveredBindings,
  discoveryBaseBindings,
  PROVIDER_FORM_LOADED_EVENT,
  refreshApiProviderEditorControls,
  releaseCleanApiProviderEditor,
  resumeApiProviderEditor,
  updateApiKeyRevealButton,
  updateProviderBindingCount,
} from "./api-provider-settings";
import { initApiProviderSortFeature } from "./api-provider-sort";
import { initProviderModelDiscovery } from "./provider-model-discovery";
import { initProviderDiscoveryPanel } from "./provider-discovery-panel";

let apiSettingsFeatureInitialized = false;

export function initApiSettingsFeature(): void {
  if (apiSettingsFeatureInitialized) return;
  apiSettingsFeatureInitialized = true;
  const { els, state } = getLegacyBridge();
  els.apiBaseUrl?.addEventListener("input", syncSvgAuthorModelVisibility);
  // Revert / sort availability follows unsaved edits as they happen.
  els.apiProviderEditor?.addEventListener("input", refreshApiProviderEditorControls);
  els.apiProviderEditor?.addEventListener("change", refreshApiProviderEditorControls);
  const discoveryConnection = () => ({
    provider_id: String(state.apiProviderDraft?.id || ""),
    api_key_source_provider_id: String(state.apiProviderDraft?.api_key_source_provider_id || ""),
    base_url: String(els.apiBaseUrl?.value || "").trim(),
    api_key: enteredApiKey().trim(),
  });
  initProviderModelDiscovery({
    container: els.apiProviderBindings,
    connectionInputs: [els.apiBaseUrl, els.apiKey],
    getConnection: discoveryConnection,
  });
  const discovery = initProviderDiscoveryPanel({
    button: document.querySelector<HTMLButtonElement>("#discoverProviderModelsButton"),
    status: document.querySelector<HTMLElement>("#providerDiscoveryStatus"),
    results: document.querySelector<HTMLElement>("#providerDiscoveryResults"),
    connectionInputs: [els.apiBaseUrl, els.apiKey],
    getConnection: discoveryConnection,
    getModels: () => state.generationCatalog?.models || [],
    getBindings: discoveryBaseBindings,
    addChoices: addDiscoveredBindings,
  });
  // A newly loaded form must not show the previous provider's model list.
  els.apiProviderEditor?.addEventListener(PROVIDER_FORM_LOADED_EVENT, discovery.clear);
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    const bridge = getLegacyBridge();
    renderAuthSource(bridge.state.authStatus);
    if (!bridge.els.systemSettingsModal?.classList.contains("hidden") && !bridge.els.systemSettingsApiPanel?.hidden) {
      setApiSettingsFeedback("", "");
    }
  });
  Object.assign(getLegacyBridge().methods, {
    refreshHealth,
    setAuthSource,
    handleAuthSourceClick,
    renderAuthSource,
    applyAuthSourceSelection,
    authSourceDetailText,
    sourceLabel,
    currentAuthSource,
    setModeSpecificElementVisibility,
    setModeSettingsVariant,
    updateModeSpecificSettings,
    normalizeApiProvider,
    activeApiProvider,
    addProviderBinding,
    restoreApiSettings,
    persistApiSettings,
    mergeApiProviderKeys,
    refreshApiSettings,
    populateApiSettingsForm,
    currentApiProviderId,
    currentApiProviderLabel,
    addApiProvider,
    confirmDeleteApiProvider,
    copyApiProvider,
    deleteApiProvider,
    editApiProvider,
    hideApiKeyReveal,
    handleProviderBindingEditorChange,
    cancelApiProviderEdit,
    saveApiProviderEdit,
    selectApiProvider,
    selectCodexMode,
    setApiKeyRevealVisible,
    updateApiKeyRevealButton,
    updateProviderBindingCount,
    toggleApiKeyReveal,
    renderApiProviderList,
    reorderApiProviders,
    removeProviderBinding,
    toggleApiProviderSortMode,
    releaseCleanApiProviderEditor,
    resumeApiProviderEditor,
    openGenerationProviderSettings,
    openApiSettingsModal,
    closeApiSettingsModal,
    currentApiImageModel,
    currentApiMode,
    currentCodexMode,
    apiModeLabel,
    codexModeLabel,
    taskBackendValue,
    taskApiProviderId,
    taskApiProviderLabel,
    taskBackendLabel,
    setApiSettingsFeedback,
  });
  initApiProviderSortFeature();
}
