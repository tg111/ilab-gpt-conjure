import { getLegacyBridge } from "./state";
import { initOutputParameterKeyboard } from "./output-parameter-keyboard";
import {
  closeMainModelCombobox,
  currentMainModel,
  handleMainModelKeydown,
  mainModelOptionsForQuery,
  openMainModelCombobox,
  persistMainModel,
  renderMainModelOptions,
  restoreMainModel,
  selectMainModelOption,
} from "./main-model-combobox";
import { updateRequestPreview } from "./request-preview";
import { currentTaskParams } from "./task-params";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { restoreCurrentModelParameterDraft, saveCurrentModelParameterDraft } from "./model-parameter-drafts";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let formControlsInitialized = false;
let formControlEventsBound = false;

function syncRunButtonLabel(): void {
  if (!els.runButton || state.runTimerId) return;
  const mode = state.mode === "edit" ? "edit" : "generate";
  els.runButton.textContent = translate(mode === "edit" ? "prompt.runEdit" : "prompt.run");
  els.runButton.title = translate(mode === "edit" ? "prompt.runEditTitle" : "prompt.runTitle");
}

export function bindFormControlEvents(): void {
  if (formControlEventsBound) return;
  formControlEventsBound = true;
  initOutputParameterKeyboard();

  document.querySelectorAll("[data-mode]").forEach((button: any) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });

  const handleMainModelChange = () => {
    persistMainModel();
    updateRequestPreview();
  };
  els.mainModel?.addEventListener("input", handleMainModelChange);
  els.mainModel?.addEventListener("change", handleMainModelChange);
  els.mainModel?.addEventListener("focus", () => openMainModelCombobox({ showAll: true }));
  els.mainModel?.addEventListener("click", () => {
    if (!state.mainModelComboboxOpen) openMainModelCombobox({ showAll: true });
  });
  els.mainModel?.addEventListener("input", () => {
    state.mainModelShowAllOptions = false;
    openMainModelCombobox();
    renderMainModelOptions();
  });
  els.mainModel?.addEventListener("keydown", handleMainModelKeydown);
  els.mainModelToggle?.addEventListener("click", (event: any) => {
    event.preventDefault();
    if (state.mainModelComboboxOpen) {
      closeMainModelCombobox();
    } else {
      openMainModelCombobox({ showAll: true });
      els.mainModel?.focus();
    }
  });
  document.addEventListener("click", (event: any) => {
    if (!els.mainModelCombobox || els.mainModelCombobox.contains(event.target)) return;
    closeMainModelCombobox();
  });
}

export function setMode(mode: any): void {
  saveCurrentModelParameterDraft();
  state.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((button: any) => {
    button.classList.toggle("active", button.dataset.mode === mode);
  });
  if (!state.runTimerId) {
    syncRunButtonLabel();
  }
  bridge.methods.renderProviderSelection?.();
  restoreCurrentModelParameterDraft();
  bridge.methods.updateModeSpecificSettings?.();
  bridge.methods.updateRequestPreview?.();
}

export function initFormControlsFeature(): void {
  if (formControlsInitialized) return;
  formControlsInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, syncRunButtonLabel);
  Object.assign(getLegacyBridge().methods, {
    bindFormControlEvents,
    setMode,
    syncRunButtonLabel,
    currentTaskParams,
    currentMainModel,
    restoreMainModel,
    persistMainModel,
    updateRequestPreview,
    mainModelOptionsForQuery,
    openMainModelCombobox,
    closeMainModelCombobox,
    renderMainModelOptions,
    selectMainModelOption,
    handleMainModelKeydown,
  });
}
