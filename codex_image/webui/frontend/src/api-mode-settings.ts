import { getLegacyBridge } from "./state";
import { selectedProviderBinding } from "./provider-selection";
import { closeMainModelCombobox } from "./main-model-combobox";
import { resolveModeSettingsVisibility, type ModeSettingsVisibility } from "./mode-settings-visibility";

const bridge = getLegacyBridge();
const els = bridge.els;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function currentAuthSource(): string { return legacyMethod("currentAuthSource"); }
function currentApiMode(): string { return legacyMethod("currentApiMode"); }
function currentCodexMode(): string { return legacyMethod("currentCodexMode"); }

export function setModeSpecificElementVisibility(element: any, visible: any): void {
  if (!element) return;
  element.setAttribute("aria-hidden", visible ? "false" : "true");
  if (visible) {
    element.classList.remove("hidden");
    element.classList.remove("mode-collapsed");
    return;
  }
  element.classList.add("mode-collapsed");
  element.classList.add("hidden");
}

function applyModeSettingsVisibility(visibility: ModeSettingsVisibility): void {
  // Prompt processing is disabled, so only the main model uses this slot.
  const showModeSettings = visibility.showMainModel;
  els.modeSpecificSettings?.classList.toggle("without-main-model", !visibility.showMainModel);
  if (!visibility.showMainModel) closeMainModelCombobox();
  setModeSpecificElementVisibility(els.modeSettingsSlot, showModeSettings);
  setModeSpecificElementVisibility(els.modeSpecificSettings, showModeSettings);
  setModeSpecificElementVisibility(els.mainModelField, visibility.showMainModel);
}

export function setModeSettingsVariant(isDirectApi: any, visibility?: ModeSettingsVisibility): void {
  const slot = els.modeSettingsSlot;
  if (slot) {
    slot.style.height = "";
    slot.classList.remove("is-transitioning");
  }
  applyModeSettingsVisibility(visibility || resolveModeSettingsVisibility(null, Boolean(isDirectApi)));
}

export function updateModeSpecificSettings(authSource: any = currentAuthSource()): void {
  const binding = selectedProviderBinding();
  const isDirectApi = binding
    ? !binding.protocol_profile.endsWith("_responses")
    : (authSource === "api" && currentApiMode() !== "responses")
      || (authSource === "codex" && currentCodexMode() !== "responses");
  setModeSettingsVariant(isDirectApi, resolveModeSettingsVisibility(binding, isDirectApi));
  legacyMethod("syncReferenceFileAvailability");
  const refreshOutputSettingsLock = getLegacyBridge().methods.refreshOutputSettingsLock;
  if (typeof refreshOutputSettingsLock === "function") refreshOutputSettingsLock();
}
