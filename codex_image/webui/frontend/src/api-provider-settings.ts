import { resetApiAdvancedSettings } from "./api-advanced-settings";
import { updateModeSpecificSettings } from "./api-mode-settings";
import { handleProviderBindingEditorChange as updateBindingEditor } from "./api-provider-binding-editor";
import type {
  ProviderOriginChangeConfirmation,
} from "./api-provider-credentials";
import {
  clearProviderApiKeyInputs,
  evaluateProviderCredentialSave,
  isConfirmedProviderOriginChange,
} from "./api-provider-credentials";
import {
  apiProviderMatchesSearch,
  scrollActiveApiProviderCardIntoView,
  updateApiProviderListPresentation,
} from "./api-provider-list-ui";
import { applyProviderDraft, normalizeApiImagesConcurrency, normalizeApiProvider, normalizeApiSettings, normalizeCodexMode, withoutApiProvider } from "./api-provider-model";
import { apiSettingsSavePayload, patchApiSettings } from "./api-provider-save";
import {
  cancelApiProviderSortInteraction,
  isCompleteProviderOrder,
} from "./api-provider-sort";
import { refreshHealth } from "./auth-source";
import { formatTranslation, translate } from "./i18n";
import { refreshGenerationCatalog } from "./model-catalog";
import { templateForDiscoveredModel, type DiscoveredChoice } from "./provider-discovery-panel";
import {
  availableProtocolsForModel,
  bindingFromProtocol,
  bindingFromTemplate,
  openProviderBindingCard,
  readProviderBindingCards,
  renderProviderBindingCards,
  validateProviderBindingOverlaps
} from "./provider-model-bindings";
import { providerBindingSelectionKey, selectedProviderBinding } from "./provider-selection";
import { getLegacyBridge } from "./state";
import {
  API_SETTINGS_STORAGE_KEY,
  DEFAULT_API_BASE_URL,
  DEFAULT_API_IMAGE_MODEL,
  DEFAULT_API_IMAGES_CONCURRENCY,
  DEFAULT_API_MODE
} from "./state-defaults";
import { closeSystemSettingsModal, openSystemSettingsModal } from "./system-settings";
export { normalizeApiImagesConcurrency, normalizeApiProvider, normalizeApiSettings } from "./api-provider-model";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;
let apiSettingsAutosaveTimerId: number | null = null;
let apiSettingsSaving = false;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function setStatus(message: any, type?: any): void { legacyMethod("setStatus", message, type); }
function updateRequestPreview(): void { legacyMethod("updateRequestPreview"); }
function closePromptPopover(): void { legacyMethod("closePromptPopover"); }
function openConfirmPopover(...args: any[]): void { legacyMethod("openConfirmPopover", ...args); }

function appendProviderIdentity(target: HTMLElement, provider: any, className: string): void {
  const icon = String(provider?.icon_emoji || "").trim();
  if (icon) {
    const emoji = document.createElement("span");
    emoji.className = "api-provider-emoji";
    emoji.setAttribute("aria-hidden", "true");
    emoji.textContent = icon;
    target.append(emoji);
  }
  const label = document.createElement("span");
  label.className = className;
  label.textContent = provider?.name || provider?.id || "";
  target.append(label);
}

function providerById(providerId: any, settings: any = state.apiSettings): any {
  const normalized = normalizeApiSettings(settings);
  return normalized.providers.find((provider: any) => provider.id === providerId) || normalized.providers[0];
}

export function updateProviderBindingCount(): void {
  const count = readProviderBindingCards(els.apiProviderBindings).length;
  setElementText(els.providerBindingsCount, `(${count})`);
}

function providerHasApiKey(provider: any): boolean {
  return Boolean(provider?.api_key || provider?.api_key_set);
}

function providerMetaLabel(provider: any): string {
  return `${translate("apiSettings.modelBindings")} (${provider?.bindings?.length || 0})`;
}

function uniqueCopiedProviderId(provider: any): string {
  const base = String(provider?.id || provider?.name || "provider")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    || "provider";
  const existing = new Set((state.apiSettings.providers || []).map((item: any) => item.id));
  const root = `${base}-copy`;
  if (!existing.has(root)) return root;
  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${root}-${index}`;
    if (!existing.has(candidate)) return candidate;
  }
  return `provider-${Date.now()}`;
}

function copiedProviderName(provider: any): string {
  const sourceName = String(provider?.name || provider?.id || translate("apiSettings.newProvider")).trim();
  const rootName = formatTranslation("apiSettings.copyProviderName", { name: sourceName });
  const existing = new Set((state.apiSettings.providers || []).map((item: any) => String(item.name || "").trim()));
  if (!existing.has(rootName)) return rootName;
  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${rootName} ${index}`;
    if (!existing.has(candidate)) return candidate;
  }
  return `${rootName} ${Date.now()}`;
}

function setElementText(element: any, value: any): void {
  if (element) element.textContent = String(value ?? "");
}

export function setApiKeyRevealVisible(visible: boolean): void {
  if (!els.apiKey) return;
  const canReveal = Boolean(els.apiKey.value);
  const shouldReveal = Boolean(visible && canReveal);
  els.apiKey.type = shouldReveal ? "text" : "password";
  els.apiKeyRevealButton?.setAttribute("aria-pressed", shouldReveal ? "true" : "false");
  const label = translate(shouldReveal ? "apiSettings.hideApiKey" : "apiSettings.showApiKey");
  els.apiKeyRevealButton?.setAttribute("aria-label", label);
  els.apiKeyRevealButton?.setAttribute("title", label);
  els.apiKeyRevealButton?.classList.toggle("active", shouldReveal);
}

export function hideApiKeyReveal(): void {
  setApiKeyRevealVisible(false);
}

// A saved key fetched only to be shown. It is not an edit: saving and model
// discovery keep relying on the stored key, so a changed base URL still asks
// before that key is sent to the new origin.
let revealedSavedKey = "";
let revealRequest = 0;

/** The key typed into the form, excluding a saved key that is merely shown. */
export function enteredApiKey(): string {
  const value = String(els.apiKey?.value || "");
  return value && value === revealedSavedKey ? "" : value;
}

/** The provider whose stored key the open form falls back to, if any. */
function savedKeyProviderId(): string {
  const draft = state.apiProviderDraft;
  if (!apiProviderEditorActive() || !draft?.api_key_set) return "";
  if (state.apiProviderDraftIsNew) return String(draft.api_key_source_provider_id || "");
  return String(draft.id || "");
}

export function updateApiKeyRevealButton(): void {
  if (!els.apiKeyRevealButton) return;
  const hasValue = Boolean(els.apiKey?.value);
  if (hasValue) els.apiKey?.removeAttribute("aria-invalid");
  if (!hasValue) hideApiKeyReveal();
  els.apiKeyRevealButton.disabled = !hasValue && !savedKeyProviderId();
  const label = translate(els.apiKey?.type === "text" ? "apiSettings.hideApiKey" : "apiSettings.showApiKey");
  els.apiKeyRevealButton.setAttribute("aria-label", label);
  els.apiKeyRevealButton.setAttribute("title", label);
}

async function fetchSavedApiKey(providerId: string): Promise<string> {
  const response = await fetch("/api/api-settings/reveal-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider_id: providerId }),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || typeof payload?.api_key !== "string") throw new Error("apiSettings.revealKeyFailed");
  return payload.api_key;
}

/** Shows or hides the key; an empty field shows the provider's saved key. */
export async function toggleApiKeyReveal(): Promise<void> {
  if (!els.apiKey || els.apiKeyRevealButton?.disabled) return;
  if (els.apiKey.type === "text") {
    hideApiKeyReveal();
    return;
  }
  if (!els.apiKey.value) {
    const providerId = savedKeyProviderId();
    if (!providerId) return;
    const request = ++revealRequest;
    const editingId = state.apiProviderEditingId;
    try {
      const key = await fetchSavedApiKey(providerId);
      // The form may have moved to another provider, or the user typed meanwhile.
      if (request !== revealRequest || state.apiProviderEditingId !== editingId || els.apiKey.value) return;
      revealedSavedKey = key;
      els.apiKey.value = key;
    } catch {
      setApiSettingsFeedback(translate("apiSettings.revealKeyFailed"), "error");
      return;
    }
  }
  setApiKeyRevealVisible(true);
  updateApiKeyRevealButton();
}

function scrollApiProviderEditorIntoView(): void {
  window.requestAnimationFrame(() => {
    els.apiProviderEditor?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  });
}

// The provider list stays beside the editor: picking a provider opens its
// form directly instead of a read-only summary with a separate Edit step.
function setApiProviderEditorVisible(visible: boolean): void {
  els.apiProviderEditor?.classList.toggle("hidden", !visible);
  els.apiProviderEditor?.setAttribute("aria-hidden", visible ? "false" : "true");
  if (!visible) hideApiKeyReveal();
}

function apiProviderEditorActive(): boolean {
  return Boolean(state.apiProviderEditingId && state.apiProviderDraft);
}

let draftBaseline = "";
/** Fired on the editor whenever it is (re)loaded with a provider. */
export const PROVIDER_FORM_LOADED_EVENT = "provider-form-loaded";

function draftSnapshot(): string {
  try {
    return JSON.stringify(draftProviderFromForm());
  } catch {
    return "";
  }
}

/** True once the open form differs from what it was loaded with. */
export function apiProviderDraftDirty(): boolean {
  return apiProviderEditorActive() && draftSnapshot() !== draftBaseline;
}

function apiSettingsPanelOpen(): boolean {
  const modal = els.systemSettingsModal as HTMLElement | null | undefined;
  const panel = els.systemSettingsApiPanel as HTMLElement | null | undefined;
  return Boolean(modal && panel && !modal.classList.contains("hidden") && !panel.hidden);
}

/** The provider highlighted in the list: the one being edited, if any. */
function listedProviderId(settings: any): string {
  if (state.apiProviderDraftIsNew) return "";
  if (apiProviderEditorActive()) return state.apiProviderEditingId;
  return settings.active_provider_id;
}

export function refreshApiProviderEditorControls(): void {
  const editing = apiProviderEditorActive();
  const isNew = Boolean(state.apiProviderDraftIsNew);
  const dirty = apiProviderDraftDirty();
  const cancel = els.cancelApiProviderEditButton as HTMLButtonElement | null;
  if (cancel) {
    const key = isNew ? "action.cancel" : "apiSettings.revertChanges";
    cancel.dataset.i18n = key;
    cancel.textContent = translate(key);
    cancel.disabled = !editing || (!isNew && !dirty);
  }
  if (els.copyApiProviderButton) els.copyApiProviderButton.disabled = !editing || isNew;
  if (els.deleteApiProviderButton) {
    els.deleteApiProviderButton.disabled = !editing || isNew
      || normalizeApiSettings(state.apiSettings).providers.length <= 1;
  }
  if (els.sortApiProvidersButton && !state.apiProviderSortMode) {
    els.sortApiProvidersButton.disabled = dirty || isNew
      || normalizeApiSettings(state.apiSettings).providers.length <= 1;
  }
}

/** Runs `action` at once, or after confirming that unsaved edits may be dropped. */
function confirmDiscardThen(anchor: HTMLElement | null | undefined, action: () => void): void {
  if (!apiProviderDraftDirty()) {
    action();
    return;
  }
  openConfirmPopover(anchor || els.saveApiProviderEditButton, {
    title: translate("apiSettings.discardChangesTitle"),
    message: translate("apiSettings.discardChangesMessage"),
    confirmText: translate("apiSettings.discardChanges"),
    focusCancel: true,
    onConfirm: action,
  });
}

function beginEditingProvider(providerId?: string, options: { keepFeedback?: boolean } = {}): void {
  const settings = normalizeApiSettings(state.apiSettings);
  const provider = settings.providers.find((item: any) => item.id === providerId)
    || settings.providers.find((item: any) => item.id === settings.active_provider_id)
    || settings.providers[0];
  if (!provider) return;
  // Local only: which provider the list shows does not change what generates.
  state.apiSettings = normalizeApiSettings({ ...settings, active_provider_id: provider.id });
  persistApiSettings();
  state.apiProviderSortMode = false;
  state.apiProviderEditingId = provider.id;
  state.apiProviderDraftIsNew = false;
  state.apiProviderDraft = normalizeApiProvider({
    ...provider,
    default_model_ids: Object.keys(state.apiSettings.default_provider_by_model || {})
      .filter((modelId) => state.apiSettings.default_provider_by_model[modelId] === provider.id),
  }, 0);
  populateApiSettingsForm();
  if (!options.keepFeedback) setApiSettingsFeedback("", "");
}

/** Opens the form for `providerId` (or the listed provider) when none is open. */
export function resumeApiProviderEditor(providerId?: string): void {
  if (apiSettingsSaving || state.apiProviderSortMode || apiProviderEditorActive()) return;
  if (!apiSettingsPanelOpen()) return;
  // Keeps a message such as "saved" from the step that closed the form.
  beginEditingProvider(providerId, { keepFeedback: true });
}

/** Closing settings drops an untouched form so background saves are not held. */
export function releaseCleanApiProviderEditor(): void {
  if (!apiProviderEditorActive() || apiProviderDraftDirty()) return;
  state.apiProviderEditingId = null;
  state.apiProviderDraft = null;
  state.apiProviderDraftIsNew = false;
  setApiProviderEditorVisible(false);
}

export function syncSvgAuthorModelVisibility(): void {
  let official = false;
  try {
    const url = new URL(els.apiBaseUrl?.value || DEFAULT_API_BASE_URL);
    official = url.origin === "https://api.openai.com" && !url.username && !url.password;
  } catch {
    // An incomplete URL is allowed while editing.
  }
  els.apiSvgAuthorModelField?.classList.toggle("hidden", !official);
}

function draftProviderFromForm(): any {
  const draft = state.apiProviderDraft || activeApiProvider();
  const bindingCards = readProviderBindingCards(els.apiProviderBindings);
  return normalizeApiProvider({
    ...draft,
    name: els.apiProviderName?.value || draft.name,
    icon_emoji: els.apiProviderIconEmoji ? els.apiProviderIconEmoji.value : draft.icon_emoji,
    base_url: els.apiBaseUrl?.value || DEFAULT_API_BASE_URL,
    svg_author_model: els.apiSvgAuthorModel?.value ?? draft.svg_author_model,
    api_key: enteredApiKey(),
    concurrency: normalizeApiImagesConcurrency(els.apiImagesConcurrency?.value),
    bindings: bindingCards,
    default_model_ids: bindingCards.filter((binding) => binding.is_default).map((binding) => binding.canonical_model_id),
    api_key_set: Boolean(draft.api_key_set || draft.api_key || draft.api_key_source_provider_id),
    api_key_masked: draft.api_key_masked,
    api_key_source_provider_id: draft.api_key_source_provider_id,
  }, 0);
}

function writeProviderForm(provider: any): void {
  if (els.apiProviderName) els.apiProviderName.value = provider.name || "";
  if (els.apiProviderIconEmoji) els.apiProviderIconEmoji.value = provider.icon_emoji || "";
  if (els.apiBaseUrl) els.apiBaseUrl.value = provider.base_url || DEFAULT_API_BASE_URL;
  if (els.apiSvgAuthorModel) els.apiSvgAuthorModel.value = provider.svg_author_model || "";
  syncSvgAuthorModelVisibility();
  if (els.apiImagesConcurrency) els.apiImagesConcurrency.value = String(normalizeApiImagesConcurrency(provider.concurrency ?? provider.images_concurrency));
  revealedSavedKey = "";
  revealRequest += 1;
  if (els.apiKey) {
    els.apiKey.value = provider.api_key || "";
    els.apiKey.placeholder = provider.api_key_set && !provider.api_key
      ? translate("apiSettings.savedKeyPlaceholder")
      : "sk-...";
  }
  hideApiKeyReveal();
  updateApiKeyRevealButton();
  renderProviderBindingCards(
    els.apiProviderBindings,
    provider.bindings || [],
    state.generationCatalog?.models || [],
    provider.id,
    defaultsForProviderDraft(provider),
  );
  updateProviderBindingCount();
  resetApiAdvancedSettings();
}

function defaultsForProviderDraft(provider: any): Record<string, string> {
  const defaults = { ...(state.apiSettings.default_provider_by_model || {}) };
  Object.keys(defaults).forEach((modelId) => {
    if (defaults[modelId] === provider.id) delete defaults[modelId];
  });
  (provider.default_model_ids || []).forEach((modelId: string) => { defaults[modelId] = provider.id; });
  return defaults;
}

export function renderApiProviderList(): void {
  cancelApiProviderSortInteraction(true);
  const settings = normalizeApiSettings(state.apiSettings);
  state.apiSettings = settings;
  const sorting = Boolean(state.apiProviderSortMode && settings.providers.length > 1);
  const searchQuery = updateApiProviderListPresentation(settings.providers.length, sorting);
  setElementText(els.apiProviderCount, formatTranslation("apiSettings.providerCount", {
    count: String(settings.providers.length),
  }));
  if (els.sortApiProvidersButton) {
    const canSort = settings.providers.length > 1;
    els.sortApiProvidersButton.classList.toggle("hidden", !canSort);
    els.sortApiProvidersButton.classList.toggle("active", sorting);
    els.sortApiProvidersButton.disabled = !canSort || (!sorting && (apiProviderDraftDirty() || Boolean(state.apiProviderDraftIsNew)));
    els.sortApiProvidersButton.textContent = translate(sorting ? "apiSettings.finishSortProviders" : "apiSettings.sortProviders");
    els.sortApiProvidersButton.setAttribute("aria-pressed", sorting ? "true" : "false");
  }
  els.addApiProviderButton?.classList.toggle("hidden", sorting);
  if (!els.apiProviderList) return;
  els.apiProviderList.classList.toggle("is-sorting", sorting);
  els.apiProviderList.setAttribute("role", sorting ? "list" : "listbox");
  if (sorting) {
    const rows = settings.providers.map((provider: any) => {
      const row = document.createElement("div");
      row.className = `api-provider-sort-row${provider.id === listedProviderId(settings) ? " active" : ""}`;
      row.dataset.apiProviderId = provider.id;
      row.setAttribute("role", "listitem");
      const content = document.createElement("div");
      content.className = "api-provider-sort-content";
      const name = document.createElement("strong");
      name.className = "api-provider-sort-name";
      appendProviderIdentity(name, provider, "api-provider-choice-label");
      const meta = document.createElement("span");
      meta.textContent = providerMetaLabel(provider);
      content.append(name, meta);
      const handle = document.createElement("button");
      handle.type = "button";
      handle.className = "api-provider-sort-handle";
      handle.dataset.apiProviderId = provider.id;
      handle.dataset.apiProviderSortHandle = "";
      const handleLabel = formatTranslation("apiSettings.sortProviderHandleAria", {
        provider: provider.name || provider.id,
      });
      handle.setAttribute("aria-label", handleLabel);
      handle.setAttribute("title", handleLabel);
      const grip = document.createElement("span");
      grip.className = "api-provider-sort-grip";
      grip.setAttribute("aria-hidden", "true");
      for (let dotIndex = 0; dotIndex < 6; dotIndex += 1) {
        grip.append(document.createElement("span"));
      }
      handle.append(grip);
      row.append(content, handle);
      return row;
    });
    els.apiProviderList.replaceChildren(...rows);
    return;
  }
  const visibleProviders = settings.providers.filter((provider: any) => apiProviderMatchesSearch(provider, searchQuery));
  const buttons = visibleProviders.map((provider: any) => {
    const button = document.createElement("button");
    const active = provider.id === listedProviderId(settings);
    button.type = "button";
    button.className = `api-provider-choice${active ? " active" : ""}`;
    button.dataset.apiProviderId = provider.id;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", active ? "true" : "false");
    const name = document.createElement("strong");
    name.className = "api-provider-choice-name";
    appendProviderIdentity(name, provider, "api-provider-choice-label");
    const meta = document.createElement("span");
    meta.textContent = providerMetaLabel(provider);
    button.append(name, meta);
    if (active) {
      const check = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      check.classList.add("api-provider-choice-check");
      check.setAttribute("viewBox", "0 0 24 24");
      check.setAttribute("aria-hidden", "true");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", "M9 16.2 4.8 12l-1.6 1.6L9 19.4 21 7.4l-1.6-1.6Z");
      check.append(path);
      button.append(check);
    }
    return button;
  });
  if (!buttons.length) {
    const empty = document.createElement("div");
    empty.className = "api-provider-search-empty";
    empty.textContent = translate("apiSettings.noProviderSearchResults");
    els.apiProviderList.replaceChildren(empty);
    return;
  }
  els.apiProviderList.replaceChildren(...buttons);
  if (!searchQuery) scrollActiveApiProviderCardIntoView(listedProviderId(settings), "center");
}

function renderApiProviderEditor(): void {
  const editing = apiProviderEditorActive();
  setApiProviderEditorVisible(editing);
  if (!editing) return;
  const isNew = Boolean(state.apiProviderDraftIsNew);
  setElementText(els.apiProviderEditorTitle, translate(isNew ? "apiSettings.newProviderTitle" : "apiSettings.editProvider"));
  writeProviderForm(state.apiProviderDraft);
  draftBaseline = draftSnapshot();
  refreshApiProviderEditorControls();
  els.apiProviderEditor?.dispatchEvent(new Event(PROVIDER_FORM_LOADED_EVENT));
}

export function activeApiProvider(): any {
  const settings = normalizeApiSettings(state.apiSettings);
  state.apiSettings = settings;
  return settings.providers.find((provider: any) => provider.id === settings.active_provider_id) || settings.providers[0];
}

export function restoreApiSettings(): void {
  try {
    const saved = JSON.parse(localStorage.getItem(API_SETTINGS_STORAGE_KEY) || "{}");
    state.apiSettings = normalizeApiSettings(saved);
  } catch {
    state.apiSettings = normalizeApiSettings();
  }
}

export function persistApiSettings(): void {
  try {
    localStorage.setItem(API_SETTINGS_STORAGE_KEY, JSON.stringify({
      codex_mode: state.apiSettings.codex_mode,
      active_provider_id: state.apiSettings.active_provider_id,
      default_provider_by_model: state.apiSettings.default_provider_by_model,
      providers: state.apiSettings.providers.map((provider: any) => ({
        id: provider.id,
        name: provider.name,
        icon_emoji: provider.icon_emoji || "",
        concurrency: provider.concurrency,
        bindings: provider.bindings,
        api_key_set: provider.api_key_set,
        api_key_masked: provider.api_key_masked,
      })),
    }));
  } catch {
    // Browser storage may be unavailable in restricted contexts.
  }
}

export function mergeApiProviderKeys(serverSettings: any): any {
  const localById = new Map<string, any>((state.apiSettings.providers || []).map((provider: any) => [provider.id, provider]));
  const normalized = normalizeApiSettings(serverSettings);
  normalized.providers = normalized.providers.map((provider: any) => {
    const local = localById.get(provider.id);
    return local?.api_key ? { ...provider, api_key: local.api_key } : provider;
  });
  return normalized;
}

export async function refreshApiSettings(options: { afterRestore?: boolean } = {}): Promise<void> {
  try {
    const response = await fetch("/api/api-settings");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || translate("apiSettings.loadFailed"));
    state.apiSettings = mergeApiProviderKeys(data.settings || {});
    populateApiSettingsForm({ preserveEditor: true });
    if (options.afterRestore && apiProviderEditorActive()) {
      setApiSettingsFeedback(translate("userConfigBackup.settingsUpdatedDraftKept"), "");
    }
    renderAuthSourceAfterProviderChange();
  } catch (error: any) {
    setApiSettingsFeedback(error.message || translate("apiSettings.loadFailed"), "error");
  }
}

export function populateApiSettingsForm(options: { preserveEditor?: boolean } = {}): void {
  const provider = activeApiProvider();
  if (els.apiProvider) {
    els.apiProvider.innerHTML = "";
    state.apiSettings.providers.forEach((item: any) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name || item.id;
      els.apiProvider.append(option);
    });
    els.apiProvider.value = provider.id;
  }
  renderApiProviderList();
  if (!options.preserveEditor || !apiProviderEditorActive()) renderApiProviderEditor();
  else refreshApiProviderEditorControls();
  updateModeSpecificSettings();
  resumeApiProviderEditor();
}

export function readApiSettingsForm(options: any = {}): any {
  const settings = normalizeApiSettings(state.apiSettings);
  state.apiSettings = options.applyProviderDraft ? applyApiProviderDraft(settings) : normalizeApiSettings(settings);
  return state.apiSettings;
}

export function currentApiProviderId(): string {
  if (state.selectedProviderId && state.selectedProviderId !== "codex") return state.selectedProviderId;
  return activeApiProvider().id;
}

export function currentApiProviderLabel(): string {
  const selected = state.generationCatalog?.providers.find((provider: any) => provider.id === state.selectedProviderId);
  if (selected) return String(selected.name || selected.id);
  const provider = activeApiProvider();
  return String(provider.name || provider.id || "").trim() || provider.id;
}

export function addApiProvider(): void {
  if (apiSettingsSaving) return;
  confirmDiscardThen(els.addApiProviderButton, startNewApiProvider);
}

function startNewApiProvider(): void {
  state.apiProviderSortMode = false;
  const id = `provider-${Date.now()}`;
  state.apiProviderEditingId = id;
  state.apiProviderDraftIsNew = true;
  state.apiProviderDraft = normalizeApiProvider({
    id,
    name: translate("apiSettings.newProvider"),
    base_url: DEFAULT_API_BASE_URL,
    concurrency: DEFAULT_API_IMAGES_CONCURRENCY,
    bindings: [bindingFromProtocol(`${id}-gpt-image-2`, "gpt-image-2", DEFAULT_API_IMAGE_MODEL, "openai_images")],
  }, state.apiSettings.providers.length);
  populateApiSettingsForm();
  setApiSettingsFeedback(translate("apiSettings.newDraftStatus"), "running");
  scrollApiProviderEditorIntoView();
  els.apiProviderName?.focus();
}

export function copyApiProvider(): void {
  if (apiSettingsSaving || state.apiProviderDraftIsNew) return;
  confirmDiscardThen(els.copyApiProviderButton, startProviderCopy);
}

function startProviderCopy(): void {
  state.apiProviderSortMode = false;
  const provider = providerById(state.apiProviderEditingId || activeApiProvider().id);
  const copiesSavedKey = providerHasApiKey(provider);
  const id = uniqueCopiedProviderId(provider);
  state.apiProviderEditingId = id;
  state.apiProviderDraftIsNew = true;
  state.apiProviderDraft = normalizeApiProvider({
    ...provider,
    bindings: provider.bindings.map((binding: any, index: number) => ({ ...binding, id: `${id}-binding-${index + 1}` })),
    id,
    name: copiedProviderName(provider),
    api_key: "",
    api_key_set: copiesSavedKey,
    api_key_masked: provider.api_key_masked || "",
    api_key_source_provider_id: copiesSavedKey ? provider.id : "",
  }, state.apiSettings.providers.length);
  populateApiSettingsForm();
  setApiSettingsFeedback(translate(copiesSavedKey ? "apiSettings.copyProviderStatus" : "apiSettings.copyProviderWithoutKeyStatus"), "running");
  scrollApiProviderEditorIntoView();
  els.apiProviderName?.focus();
}

export async function deleteApiProvider(): Promise<void> {
  if (apiSettingsSaving || state.apiProviderDraftIsNew) return;
  const activeId = state.apiProviderEditingId || state.apiSettings.active_provider_id;
  const candidate = withoutApiProvider(state.apiSettings, activeId);
  if (!candidate) return;
  // Deleting discards the open form; autosave refuses to run while one is open.
  state.apiProviderEditingId = null;
  state.apiProviderDraft = null;
  state.apiProviderDraftIsNew = false;
  if (!await saveApiSettings({ auto: true, candidateSettings: candidate })) {
    resumeApiProviderEditor(activeId);
    els.deleteApiProviderButton?.focus({ preventScroll: true });
    return;
  }
  // A failed write leaves both the list and generation selection untouched.
  Object.entries(state.lastProviderByModel || {}).forEach(([modelId, providerId]) => {
    if (providerId === activeId) delete state.lastProviderByModel[modelId];
  });
  Object.entries(state.lastProviderSelectionByModel || {}).forEach(([modelId, selection]) => {
    if (String(selection).startsWith(`${activeId}::`)) delete state.lastProviderSelectionByModel[modelId];
  });
  getLegacyBridge().methods.persistModelSelection?.();
  if (state.apiSettings.providers.length <= 1) state.apiProviderSortMode = false;
  populateApiSettingsForm();
  renderAuthSourceAfterProviderChange();
  scrollActiveApiProviderCardIntoView(activeApiProvider().id, "nearest");
  (els.apiProviderList as HTMLElement | null)?.querySelector<HTMLElement>("[aria-selected='true']")?.focus({ preventScroll: true });
}

export function confirmDeleteApiProvider(anchor: any = els.deleteApiProviderButton): void {
  if (apiSettingsSaving || state.apiProviderDraftIsNew) return;
  if (state.apiSettings.providers.length <= 1) return;
  const provider = providerById(state.apiProviderEditingId || activeApiProvider().id);
  openConfirmPopover(anchor || els.deleteApiProviderButton, {
    title: translate("apiSettings.deleteProviderTitle"),
    message: formatTranslation("apiSettings.deleteProviderMessage", {
      provider: provider.name || provider.id,
    }),
    detail: translate("apiSettings.deleteProviderDetail"),
    confirmText: translate("action.delete"),
    onConfirm: () => deleteApiProvider(),
  });
}

export function openApiSettingsModal(): void {
  if (apiProviderDraftDirty() || state.apiProviderDraftIsNew) {
    openSystemSettingsModal("api");
    return;
  }
  closePromptPopover();
  state.apiProviderEditingId = null;
  state.apiProviderDraft = null;
  state.apiProviderDraftIsNew = false;
  state.apiProviderSortMode = false;
  if (els.apiProviderSearch) els.apiProviderSearch.value = "";
  // Open on the provider the composer is generating with.
  const generating = state.selectedProviderId;
  if ((state.apiSettings.providers || []).some((provider: any) => provider.id === generating)) {
    state.apiSettings = normalizeApiSettings({ ...state.apiSettings, active_provider_id: generating });
  }
  setApiSettingsFeedback("", "");
  openSystemSettingsModal("api");
  resumeApiProviderEditor(activeApiProvider().id);
  scrollActiveApiProviderCardIntoView(activeApiProvider().id, "center");
}

export function openGenerationProviderSettings(): void {
  openApiSettingsModal();
}

export function closeApiSettingsModal(): void {
  closeSystemSettingsModal();
}

/**
 * Opens a provider's form. Only the composer's model menu decides which
 * provider generates, so browsing providers here never switches it.
 */
export function selectApiProvider(providerId: any, anchor?: HTMLElement | null): void {
  if (apiSettingsSaving || state.apiProviderSortMode) return;
  const id = String(providerId || "").trim();
  if (!id) return;
  if (apiProviderEditorActive() && !state.apiProviderDraftIsNew && state.apiProviderEditingId === id) return;
  confirmDiscardThen(anchor, () => {
    beginEditingProvider(id);
    scrollActiveApiProviderCardIntoView(id, "nearest");
  });
}

export function editApiProvider(): void {
  if (apiSettingsSaving || apiProviderEditorActive()) return;
  beginEditingProvider(activeApiProvider().id);
  els.apiProviderName?.focus();
}

/** Reverts the form to the saved provider, or drops a provider not yet saved. */
export function cancelApiProviderEdit(): void {
  if (apiSettingsSaving) return;
  if (!apiProviderEditorActive()) return;
  // The button disables once the form is clean again; keep focus in the dialog.
  els.systemSettingsApiTab?.focus({ preventScroll: true });
  const providerId = state.apiProviderDraftIsNew ? activeApiProvider().id : state.apiProviderEditingId;
  beginEditingProvider(providerId);
  scrollActiveApiProviderCardIntoView(activeApiProvider().id, "center");
}

export function toggleApiProviderSortMode(): void {
  if (apiSettingsSaving) return;
  if (!state.apiProviderSortMode && (apiProviderDraftDirty() || state.apiProviderDraftIsNew)) {
    setApiSettingsFeedback(translate("apiSettings.finishEditFirst"), "error");
    return;
  }
  const settings = normalizeApiSettings(state.apiSettings);
  if (settings.providers.length <= 1) return;
  cancelApiProviderSortInteraction(true);
  state.apiProviderSortMode = !state.apiProviderSortMode;
  if (state.apiProviderSortMode) {
    // The order autosaves, which an open form would hold back.
    state.apiProviderEditingId = null;
    state.apiProviderDraft = null;
    state.apiProviderDraftIsNew = false;
    setApiProviderEditorVisible(false);
  }
  renderApiProviderList();
  setApiSettingsFeedback(state.apiProviderSortMode ? translate("apiSettings.sortProviderModeStatus") : "", state.apiProviderSortMode ? "running" : "");
  if (!state.apiProviderSortMode) {
    resumeApiProviderEditor(settings.active_provider_id);
    scrollActiveApiProviderCardIntoView(settings.active_provider_id, "center");
  }
}

function focusedApiProviderSortId(): string {
  if (!state.apiProviderSortMode) return "";
  const handle = (document.activeElement as HTMLElement | null)?.closest<HTMLButtonElement>(
    "button[data-api-provider-sort-handle][data-api-provider-id]",
  );
  return handle?.dataset.apiProviderId || "";
}

function focusApiProviderSortHandle(providerId: string): void {
  if (!providerId) return;
  window.requestAnimationFrame(() => {
    const escapedId = CSS.escape(providerId);
    (els.apiProviderList as HTMLElement | null)
      ?.querySelector<HTMLButtonElement>(`button[data-api-provider-sort-handle][data-api-provider-id="${escapedId}"]`)
      ?.focus({ preventScroll: true });
  });
}

export function reorderApiProviders(orderedIds: readonly string[], focusProviderId = ""): boolean {
  if (apiSettingsSaving) return false;
  if (!state.apiProviderSortMode || apiProviderEditorActive() || !Array.isArray(orderedIds)) return false;
  const settings = normalizeApiSettings(state.apiSettings);
  const currentIds = settings.providers.map((provider: any) => provider.id);
  const candidate = orderedIds.map((id) => String(id || ""));
  if (!isCompleteProviderOrder(candidate, currentIds)) return false;
  if (candidate.every((id, index) => id === currentIds[index])) return false;
  const providersById = new Map<string, any>(
    settings.providers.map((provider: any) => [provider.id, provider]),
  );
  const providers = candidate.map((id) => providersById.get(id));
  state.apiSettings = normalizeApiSettings({
    ...settings,
    providers,
    active_provider_id: settings.active_provider_id,
  });
  persistApiSettings();
  renderApiProviderList();
  setApiSettingsFeedback(translate("apiSettings.sortProviderStatus"), "running");
  queueApiSettingsAutosave();
  focusApiProviderSortHandle(focusProviderId);
  return true;
}

export async function saveApiProviderEdit(): Promise<void> {
  if (!apiProviderEditorActive()) return;
  await saveApiSettings();
}

export function addProviderBinding(): void {
  if (!apiProviderEditorActive()) return;
  const draft = draftProviderFromForm();
  const models = state.generationCatalog?.models || [];
  const model = models.find((item: any) => !draft.bindings.some((binding: any) => binding.canonical_model_id === item.id))
    || models[0];
  if (!model) {
    setApiSettingsFeedback(translate("apiSettings.catalogRequiredForBinding"), "error");
    return;
  }
  const bindingId = `${draft.id}-binding-${Date.now()}`;
  const protocol = availableProtocolsForModel(model.id)[0];
  if (!protocol) {
    setApiSettingsFeedback(translate("apiSettings.catalogRequiredForBinding"), "error");
    return;
  }
  draft.bindings.push(bindingFromProtocol(
    bindingId,
    model.id,
    model.official_model_id || model.id,
    protocol,
    [...model.operations],
  ));
  if (!state.apiSettings.default_provider_by_model?.[model.id]) {
    draft.default_model_ids = [...new Set([...(draft.default_model_ids || []), model.id])];
  }
  state.apiProviderDraft = draft;
  renderProviderBindingCards(
    els.apiProviderBindings,
    draft.bindings,
    models,
    draft.id,
    defaultsForProviderDraft(draft),
  );
  openProviderBindingCard(els.apiProviderBindings, bindingId, { focus: true });
  updateProviderBindingCount();
  refreshApiProviderEditorControls();
}

// A new provider starts with a placeholder GPT row; picked models replace it.
function withoutPlaceholderBinding(draftId: string, bindings: any[]): any[] {
  const placeholder = bindings[0];
  return state.apiProviderDraftIsNew && bindings.length === 1 && placeholder
    && placeholder.id === `${draftId}-gpt-image-2` && placeholder.remote_model_id === DEFAULT_API_IMAGE_MODEL
    ? [] : bindings;
}

/** The form's bindings as model discovery should treat them. */
export function discoveryBaseBindings(): any[] {
  if (!apiProviderEditorActive()) return [];
  return withoutPlaceholderBinding(state.apiProviderDraft.id, readProviderBindingCards(els.apiProviderBindings));
}

/** Adds the models picked from a provider's model list; returns how many changed. */
export function addDiscoveredBindings(choices: DiscoveredChoice[]): number {
  if (!apiProviderEditorActive() || !choices.length) return 0;
  const draft = draftProviderFromForm();
  const models = state.generationCatalog?.models || [];
  let bindings = withoutPlaceholderBinding(draft.id, [...draft.bindings]);
  let changed = 0;
  const stamp = Date.now();
  choices.forEach((choice, index) => {
    const model = models.find((item: any) => item.id === choice.modelId);
    if (!model) return;
    const existing = bindings.find((binding: any) => binding.canonical_model_id === model.id);
    if (existing) {
      // One binding per model: point the existing one at the picked model name.
      if (existing.remote_model_id === choice.remote) return;
      existing.remote_model_id = choice.remote;
      changed += 1;
      return;
    }
    const template = templateForDiscoveredModel(model.id, els.apiBaseUrl?.value || "", bindings);
    bindings.push(bindingFromTemplate(`${draft.id}-${model.id}-${stamp}-${index}`, model.id, choice.remote, template, [...model.operations]));
    if (!state.apiSettings.default_provider_by_model?.[model.id]) {
      draft.default_model_ids = [...new Set([...(draft.default_model_ids || []), model.id])];
    }
    changed += 1;
  });
  if (!changed) return 0;
  draft.bindings = bindings;
  state.apiProviderDraft = draft;
  renderProviderBindingCards(els.apiProviderBindings, bindings, models, draft.id, defaultsForProviderDraft(draft));
  updateProviderBindingCount();
  refreshApiProviderEditorControls();
  return changed;
}

export function removeProviderBinding(bindingId: string): void {
  if (!apiProviderEditorActive()) return;
  const draft = draftProviderFromForm();
  if (draft.bindings.length <= 1) {
    setApiSettingsFeedback(translate("apiSettings.keepOneBinding"), "error");
    return;
  }
  draft.bindings = draft.bindings.filter((binding: any) => binding.id !== bindingId);
  state.apiProviderDraft = draft;
  renderProviderBindingCards(
    els.apiProviderBindings,
    draft.bindings,
    state.generationCatalog?.models || [],
    draft.id,
    defaultsForProviderDraft(draft),
  );
  updateProviderBindingCount();
  refreshApiProviderEditorControls();
}

function renderAuthSourceAfterProviderChange(): void {
  legacyMethod("renderAuthSource", state.authStatus);
  legacyMethod("renderProviderSelection");
  updateModeSpecificSettings();
  updateRequestPreview();
}

export function currentApiImageModel(): string {
  const provider = activeApiProvider();
  const binding = provider.bindings?.find((item: any) => item.canonical_model_id === state.selectedModelId)
    || provider.bindings?.find((item: any) => item.canonical_model_id === "gpt-image-2")
    || provider.bindings?.[0];
  return String(binding?.remote_model_id || provider.image_model || DEFAULT_API_IMAGE_MODEL).trim() || DEFAULT_API_IMAGE_MODEL;
}

export function currentApiMode(): string {
  const binding = selectedProviderBinding();
  if (binding) return String(binding.protocol_profile).includes("responses") ? "responses" : "images";
  return activeApiProvider().api_mode === "responses" ? "responses" : DEFAULT_API_MODE;
}

export function currentCodexMode(): string {
  const binding = selectedProviderBinding();
  if (state.selectedProviderId === "codex" && binding) {
    return binding.protocol_profile === "codex_responses" ? "responses" : "images";
  }
  state.apiSettings = normalizeApiSettings(state.apiSettings);
  return normalizeCodexMode(state.apiSettings.codex_mode);
}

export function currentApiImagesConcurrency(): number {
  const provider = activeApiProvider();
  return normalizeApiImagesConcurrency(provider.concurrency ?? provider.images_concurrency);
}

export function apiModeLabel(mode: any): string {
  return mode === "responses" ? "Responses" : translate("apiSettings.modeImagesShort");
}

export function codexModeLabel(mode: any): string {
  return mode === "responses" ? "Codex Responses" : "Codex Image";
}

function backendDisplayLabel(backend: string): string {
  if (backend === "codex_images") return "Codex Image";
  if (backend === "codex_responses") return "Codex Responses";
  if (backend === "openai_images") return "API Image";
  if (backend === "openai_responses") return "API Responses";
  return backend;
}

function backendModeLabel(backend: string): string {
  if (backend === "codex_images" || backend === "openai_images") return "Image";
  if (backend === "codex_responses" || backend === "openai_responses") return "Responses";
  return "";
}

export function selectCodexMode(mode: any, anchor?: HTMLElement | null): boolean {
  if (apiSettingsSaving) return false;
  const normalized = normalizeCodexMode(mode);
  void anchor;
  state.apiSettings = normalizeApiSettings({ ...state.apiSettings, codex_mode: normalized });
  legacyMethod("syncCodexCatalogMode", normalized);
  legacyMethod("selectGenerationProvider", providerBindingSelectionKey("codex", `codex-gpt-image-2-${normalized}`));
  legacyMethod("renderProviderSelection");
  updateModeSpecificSettings();
  updateRequestPreview();
  persistApiSettings();
  queueApiSettingsAutosave();
  return true;
}

export function queueApiSettingsAutosave(options: { silent?: boolean } = {}): void {
  if (apiSettingsSaving || apiProviderDraftDirty() || state.apiProviderDraftIsNew) return;
  if (apiSettingsAutosaveTimerId !== null) {
    window.clearTimeout(apiSettingsAutosaveTimerId);
  }
  setApiSettingsFeedback(options.silent ? "" : translate("apiSettings.autoSaving"), options.silent ? "" : "running");
  apiSettingsAutosaveTimerId = window.setTimeout(() => {
    apiSettingsAutosaveTimerId = null;
    void saveApiSettings({ auto: true, silent: options.silent });
  }, 260);
}

export function taskBackendValue(task: any): string {
  return String(task?.backend || task?.requested_backend || "").trim();
}

export function taskApiProviderId(task: any): string {
  return String(
    task?.api_provider_id
    || task?.params?.api_provider_id
    || task?.request?.webui_api_provider_id
    || task?.request?.api_provider_id
    || task?.provider_id
    || "",
  ).trim();
}

export function taskApiProviderLabel(task: any): string {
  const providerId = taskApiProviderId(task);
  const providerName = String(
    task?.api_provider_name
    || task?.params?.api_provider_name
    || task?.request?.webui_api_provider_name
    || task?.request?.api_provider_name
    || task?.provider
    || "",
  ).trim();
  const configuredProvider = providerId ? state.apiSettings.providers.find((provider: any) => provider.id === providerId) : null;
  const label = providerName || configuredProvider?.name || providerId;
  if (!label) return "";
  return !providerId || label === providerId ? label : `${label} (${providerId})`;
}

export function taskBackendLabel(task: any): string {
  const backend = taskBackendValue(task);
  const provider = taskApiProviderLabel(task);
  const backendLabel = backendDisplayLabel(backend);
  if (provider && backend.startsWith("openai_")) {
    return [provider, backendModeLabel(backend)].filter(Boolean).join(" · ");
  }
  return [backendLabel, provider].filter(Boolean).join(" · ");
}

export function setApiSettingsFeedback(message: any, type: any = ""): void {
  [els.apiSettingsStatus].filter(Boolean).forEach((statusElement: any) => {
    statusElement.textContent = message;
    statusElement.className = `api-settings-feedback settings-action-status ${type || ""}`.trim();
  });
}

function saveButtons(): any[] {
  return [els.saveApiProviderEditButton].filter(Boolean);
}

function setSaveButtonsDisabled(disabled: boolean): void {
  saveButtons().forEach((button) => { button.disabled = disabled; });
}

function setSaveButtonText(stateName: "saving" | "saved" | "failed" | "default"): void {
  const providerText = {
    saving: translate("apiSettings.saving"),
    saved: translate("apiSettings.savedShort"),
    failed: translate("apiSettings.saveFailedShort"),
    default: translate("action.save"),
  }[stateName];
  if (els.saveApiProviderEditButton) els.saveApiProviderEditButton.textContent = providerText;
}

export async function saveApiSettings(options: any = {}): Promise<boolean> {
  if (apiSettingsSaving) return false;
  const autoSave = Boolean(options.auto);
  const silent = autoSave && Boolean(options.silent);
  if (autoSave && (apiProviderDraftDirty() || state.apiProviderDraftIsNew)) return true;
  // An immediate deletion includes any pending selection in its one write.
  if (apiSettingsAutosaveTimerId !== null) {
    window.clearTimeout(apiSettingsAutosaveTimerId);
    apiSettingsAutosaveTimerId = null;
  }
  const sortFocusId = autoSave ? focusedApiProviderSortId() : "";
  if (state.apiSettingsSaveTimerId) {
    window.clearTimeout(state.apiSettingsSaveTimerId);
    state.apiSettingsSaveTimerId = null;
  }
  const previousSettings = normalizeApiSettings(state.apiSettings);
  const previousEditingId = state.apiProviderEditingId;
  const previousDraft = apiProviderEditorActive() ? draftProviderFromForm() : null;
  const previousDraftIsNew = state.apiProviderDraftIsNew;
  let confirmedOriginChange: ProviderOriginChangeConfirmation | null = null;
  if (!autoSave && apiProviderEditorActive()) {
    const bindings = readProviderBindingCards(els.apiProviderBindings);
    const invalidBinding = bindings.find((binding) => !binding.canonical_model_id
      || !binding.remote_model_id || !binding.operations.length);
    if (!bindings.length || invalidBinding) {
      setApiSettingsFeedback(translate("apiSettings.bindingRequiredFields"), "error");
      if (invalidBinding) {
        openProviderBindingCard(els.apiProviderBindings, invalidBinding.id, { focus: true });
        if (!invalidBinding.remote_model_id) {
          (els.apiProviderBindings as HTMLElement | null)?.querySelector<HTMLInputElement>(
            `[data-binding-id="${CSS.escape(invalidBinding.id)}"] [data-binding-remote-model]`,
          )?.focus();
        }
      }
      return false;
    }
    const overlap = validateProviderBindingOverlaps(bindings);
    if (overlap) {
      setApiSettingsFeedback(formatTranslation("apiSettings.bindingOverlap", {
        model: overlap.canonicalModelId,
        operation: overlap.operation,
      }), "error");
      openProviderBindingCard(els.apiProviderBindings, overlap.secondBindingId, { focus: true });
      return false;
    }
    const providerDraft = draftProviderFromForm();
    const credentialDecision = evaluateProviderCredentialSave(
      providerDraft,
      previousSettings.providers,
    );
    if (credentialDecision.kind === "key_required") {
      els.apiKey?.setAttribute("aria-invalid", "true");
      setApiSettingsFeedback(translate("apiSettings.apiKeyRequired"), "error");
      els.apiKey?.focus();
      return false;
    }
    const requestedConfirmation = options.originChangeConfirmation || null;
    if (credentialDecision.kind === "confirm_origin_change") {
      if (!isConfirmedProviderOriginChange(credentialDecision, requestedConfirmation)) {
        openConfirmPopover(els.saveApiProviderEditButton, {
          title: translate("apiSettings.originChangeTitle"),
          message: translate("apiSettings.originChangeMessage"),
          detail: formatTranslation("apiSettings.originChangeDetail", {
            previousOrigin: credentialDecision.previousOrigin,
            nextOrigin: credentialDecision.nextOrigin,
          }),
          cancelText: translate("apiSettings.enterNewKey"),
          confirmText: translate("apiSettings.keepKeyAndSave"),
          focusCancel: true,
          onCancel: () => els.apiKey?.focus(),
          onConfirm: () => saveApiSettings({
            originChangeConfirmation: {
              providerId: credentialDecision.providerId,
              previousOrigin: credentialDecision.previousOrigin,
              nextOrigin: credentialDecision.nextOrigin,
            },
          }),
        });
        return false;
      }
      confirmedOriginChange = requestedConfirmation;
    }
    els.apiKey?.removeAttribute("aria-invalid");
  }
  const settings = options.candidateSettings || readApiSettingsForm({ applyProviderDraft: !autoSave });
  persistApiSettings();
  const payload = apiSettingsSavePayload(settings, confirmedOriginChange);
  if (!autoSave) {
    setSaveButtonsDisabled(true);
    setSaveButtonText("saving");
  }
  if (!silent) setApiSettingsFeedback(translate(autoSave ? "apiSettings.autoSaving" : "apiSettings.savingStatus"), "running");
  apiSettingsSaving = true;
  const panel = els.systemSettingsApiPanel as HTMLElement | null;
  const previousFocus = document.activeElement as HTMLElement | null;
  panel?.setAttribute("inert", "");
  panel?.setAttribute("aria-busy", "true");
  try {
    const data = await patchApiSettings(payload);
    state.apiSettings = clearProviderApiKeyInputs(normalizeApiSettings(data.settings || {}));
    state.apiProviderEditingId = null;
    state.apiProviderDraft = null;
    state.apiProviderDraftIsNew = false;
    // Stay on the provider just saved, or the one that was open.
    const reopenId = previousDraft?.id || previousEditingId;
    if (reopenId && state.apiSettings.providers.some((provider: any) => provider.id === reopenId)) {
      state.apiSettings = normalizeApiSettings({ ...state.apiSettings, active_provider_id: reopenId });
    }
    persistApiSettings();
    populateApiSettingsForm();
    focusApiProviderSortHandle(sortFocusId);
    if (!silent) setApiSettingsFeedback(autoSave ? translate("apiSettings.autoSaved") : formatTranslation("apiSettings.savedSummary", {
      codex: codexModeLabel(currentCodexMode()),
      provider: activeApiProvider().name,
      mode: apiModeLabel(currentApiMode()),
      model: currentApiImageModel(),
      concurrency: currentApiImagesConcurrency(),
    }), "ok");
    if (!autoSave) setSaveButtonText("saved");
    state.apiSettingsSaveTimerId = window.setTimeout(() => {
      if (!autoSave) setSaveButtonText("default");
      state.apiSettingsSaveTimerId = null;
    }, 1600);
    if (!silent) setStatus(translate("apiSettings.savedStatus"), "ok");
    await refreshGenerationCatalog();
    await refreshHealth();
    updateRequestPreview();
    return true;
  } catch (error: any) {
    state.apiSettings = previousSettings;
    state.apiProviderEditingId = previousEditingId;
    state.apiProviderDraft = previousDraft;
    state.apiProviderDraftIsNew = previousDraftIsNew;
    persistApiSettings();
    populateApiSettingsForm();
    focusApiProviderSortHandle(sortFocusId);
    setApiSettingsFeedback(error.message || translate("apiSettings.saveFailed"), "error");
    if (!autoSave) setSaveButtonText("failed");
    setStatus(error.message || translate("apiSettings.saveFailed"), "error");
    return false;
  } finally {
    apiSettingsSaving = false;
    panel?.removeAttribute("inert");
    panel?.removeAttribute("aria-busy");
    resumeApiProviderEditor(state.apiSettings.active_provider_id);
    if (!autoSave) setSaveButtonsDisabled(false);
    if (previousFocus?.isConnected && panel?.contains(previousFocus)
      && !previousFocus.closest("[inert], .hidden")) previousFocus.focus({ preventScroll: true });
    if (!autoSave && !state.apiSettingsSaveTimerId && els.saveApiProviderEditButton?.textContent !== translate("action.save")) {
      state.apiSettingsSaveTimerId = window.setTimeout(() => {
        setSaveButtonText("default");
        state.apiSettingsSaveTimerId = null;
      }, 1600);
    }
  }
}

function applyApiProviderDraft(settings: any): any {
  if (!apiProviderEditorActive()) return normalizeApiSettings(settings);
  const result = applyProviderDraft(settings, draftProviderFromForm());
  state.apiProviderEditingId = null;
  state.apiProviderDraft = null;
  state.apiProviderDraftIsNew = false;
  return result;
}

export function handleProviderBindingEditorChange(event: Event): void {
  updateBindingEditor(event, {
    state: { apiProviderDraftIsNew: state.apiProviderDraftIsNew, generationCatalog: state.generationCatalog },
    els: { apiBaseUrl: els.apiBaseUrl, apiProviderBindings: els.apiProviderBindings },
    updateProviderBindingCount,
  });
}
