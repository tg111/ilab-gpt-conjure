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
  revealApiKeyWhilePressed,
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
  updateApiKeyRevealButton,
  updateProviderBindingCount,
} from "./api-provider-settings";
import { initApiProviderSortFeature } from "./api-provider-sort";
import { initProviderModelDiscovery } from "./provider-model-discovery";

let apiSettingsFeatureInitialized = false;

export function initApiSettingsFeature(): void {
  if (apiSettingsFeatureInitialized) return;
  apiSettingsFeatureInitialized = true;
  const { els, state } = getLegacyBridge();
  els.apiBaseUrl?.addEventListener("input", syncSvgAuthorModelVisibility);
  initProviderModelDiscovery({
    container: els.apiProviderBindings,
    connectionInputs: [els.apiBaseUrl, els.apiKey],
    getConnection: () => ({
      provider_id: String(state.apiProviderDraft?.id || ""),
      api_key_source_provider_id: String(state.apiProviderDraft?.api_key_source_provider_id || ""),
      base_url: String(els.apiBaseUrl?.value || "").trim(),
      api_key: String(els.apiKey?.value || "").trim(),
    }),
  });
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
    revealApiKeyWhilePressed,
    renderApiProviderList,
    reorderApiProviders,
    removeProviderBinding,
    toggleApiProviderSortMode,
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
