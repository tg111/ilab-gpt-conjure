/**
 * Desktop "studio" layout: results take the stage, the composer sits at the
 * bottom, parameters collapse into pills and the model picker lives in the
 * composer. Existing controls are moved, never recreated, so their state and
 * handlers stay intact; leaving the desktop width puts everything back.
 */
import type { CatalogModel, CatalogParameterDefinition, GenerationOperation } from "./types";
import { getLegacyBridge } from "./state";
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { currentGenerationSelection } from "./generation-request";
import { requestedSize } from "./image-size-editor";
import { eligibleProviderBindings, selectGenerationProvider, type EligibleProviderBinding } from "./provider-selection";
import { selectConcreteModel } from "./model-selection";
import { modelFamilyBrandMarkHtml } from "./model-family-icons";
import { refreshSegmentedIndicators } from "./segmented-indicator";
import { createStudioRecipes } from "./studio-recipes";

export const STUDIO_QUERY = "(min-width: 1181px)";

const PILL_PARAMETER_IDS = new Set([
  "canvas.mode",
  "canvas.aspect_ratio",
  "canvas.resolution",
  "canvas.size",
  "output.count",
  "gpt.quality",
]);

type PillTarget = "size" | "canvas.resolution" | "output.count" | "gpt.quality" | "more";

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

function sameValue(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function valueLabel(definition: CatalogParameterDefinition, value: unknown): string {
  if (definition.value_type === "boolean") return value ? translate(definition.label_key) : "";
  if (definition.value_type === "object") return translate(definition.label_key);
  const key = definition.value_label_keys?.[definition.allowed_values.indexOf(value)];
  return key ? translate(key) : String(value);
}

function currentModel(): CatalogModel | undefined {
  const { state } = getLegacyBridge();
  return state.generationCatalog?.models.find((item) => item.id === state.selectedModelId);
}

interface PillSpec {
  target: PillTarget;
  label: string;
  value: string;
  changed?: boolean;
}

export function studioPillSpecs(model: CatalogModel | undefined, parameters: Record<string, unknown>): PillSpec[] {
  if (!model) return [];
  const definitions = new Map(model.parameters.map((definition) => [definition.id, definition]));
  const pills: PillSpec[] = [];
  const mode = parameters["canvas.mode"];
  if (mode === "auto") {
    pills.push({ target: "size", label: "", value: translate("output.sizeAuto") });
  } else if (mode === "custom") {
    const size = requestedSize(model, parameters);
    pills.push({ target: "size", label: "", value: size ? size.replace("x", " × ") : translate("output.sizeAuto") });
  } else if (parameters["canvas.aspect_ratio"] !== undefined) {
    pills.push({ target: "size", label: "", value: String(parameters["canvas.aspect_ratio"]) });
  }
  if (mode !== "custom" && mode !== "auto" && parameters["canvas.resolution"] !== undefined) {
    pills.push({ target: "canvas.resolution", label: "", value: String(parameters["canvas.resolution"]) });
  }
  if (parameters["output.count"] !== undefined) {
    pills.push({ target: "output.count", label: "", value: `× ${Number(parameters["output.count"]) || 1}` });
  }
  const quality = definitions.get("gpt.quality");
  if (quality && parameters["gpt.quality"] !== undefined) {
    pills.push({ target: "gpt.quality", label: translate(quality.label_key), value: valueLabel(quality, parameters["gpt.quality"]) });
  }
  const changed = Object.entries(parameters)
    .filter(([id]) => !PILL_PARAMETER_IDS.has(id))
    .flatMap(([id, value]) => {
      const definition = definitions.get(id);
      if (!definition || sameValue(value, definition.default)) return [];
      const label = valueLabel(definition, value);
      return label ? [label] : [];
    });
  pills.push({
    target: "more",
    label: "",
    value: changed.length ? changed.slice(0, 2).join(" · ") + (changed.length > 2 ? ` +${changed.length - 2}` : "") : translate("studio.moreParameters"),
    changed: changed.length > 0,
  });
  return pills;
}

function bindingLabel(entry: EligibleProviderBinding): string {
  return entry.binding.display_name || entry.provider.name;
}

export function initStudioComposer(): void {
  const query = window.matchMedia(STUDIO_QUERY);
  const controls = document.querySelector<HTMLElement>(".controls-col");
  const promptPanel = document.querySelector<HTMLElement>(".prompt-panel");
  const promptCompose = promptPanel?.querySelector<HTMLElement>(".prompt-compose");
  const outputPanel = document.querySelector<HTMLElement>(".output-panel");
  const runButton = document.getElementById("runButton");
  const summary = document.getElementById("executionSummary");
  const grid = document.getElementById("modelParameterGrid");
  if (!controls || !promptPanel || !promptCompose || !outputPanel || !runButton || !summary || !grid) return;

  const bar = element("div", "studio-pill-bar");
  bar.id = "studioPillBar";
  const modelPill = element("button", "studio-pill studio-model-pill");
  modelPill.type = "button";
  modelPill.id = "studioModelPill";
  modelPill.setAttribute("aria-haspopup", "dialog");
  modelPill.setAttribute("aria-expanded", "false");
  modelPill.setAttribute("aria-controls", "studioModelMenu");
  const parameterPills = element("div", "studio-parameter-pills");
  const runSlot = element("div", "studio-run-slot");
  const describeCurrent = () => {
    const model = currentModel();
    const selection = currentGenerationSelection();
    const provider = getLegacyBridge().state.generationCatalog?.providers.find((item) => item.id === selection.providerId);
    const values = studioPillSpecs(model, selection.parameters)
      .filter((spec) => spec.target !== "more" || spec.changed)
      .map((spec) => [spec.label, spec.value].filter(Boolean).join(" "));
    return [model?.display_name, provider?.name, ...values].filter(Boolean).join(" · ");
  };
  const recipes = createStudioRecipes(describeCurrent, () => {
    closeModelMenu();
    closeParams();
  });
  bar.append(modelPill, parameterPills, recipes.button, runSlot);

  const modelMenu = element("div", "studio-popover studio-model-menu");
  modelMenu.id = "studioModelMenu";
  modelMenu.setAttribute("role", "dialog");
  modelMenu.hidden = true;


  const runMarker = document.createComment("studio-run-origin");
  let active = false;

  function closeModelMenu() {
    modelMenu.hidden = true;
    modelPill.setAttribute("aria-expanded", "false");
  }
  function closeParams() {
    document.body.removeAttribute("data-studio-params-open");
    parameterPills.querySelectorAll("[aria-expanded]").forEach((pill) => pill.setAttribute("aria-expanded", "false"));
  }

  const openParams = (target: PillTarget, pill: HTMLElement) => {
    closeModelMenu();
    recipes.close();
    const wasOpen = document.body.hasAttribute("data-studio-params-open");
    const sameTarget = pill.getAttribute("aria-expanded") === "true";
    closeParams();
    if (wasOpen && sameTarget) return;
    document.body.setAttribute("data-studio-params-open", "");
    pill.setAttribute("aria-expanded", "true");
    const id = target === "size" ? "canvas.mode" : target;
    const field = target === "more"
      ? null
      : grid.querySelector<HTMLElement>(`[data-parameter-id="${CSS.escape(id)}"]`)
        || (target === "size" ? grid.querySelector<HTMLElement>('[data-parameter-id="canvas.aspect_ratio"]') : null);
    grid.querySelectorAll(".studio-field-focus").forEach((node) => node.classList.remove("studio-field-focus"));
    // Segment indicators measure their buttons, which had no size while hidden.
    refreshSegmentedIndicators();
    if (field) {
      field.classList.add("studio-field-focus");
      field.scrollIntoView({ block: "nearest" });
    }
  };

  const renderPills = () => {
    const model = currentModel();
    const selection = currentGenerationSelection();
    const { state } = getLegacyBridge();
    const provider = state.generationCatalog?.providers.find((item) => item.id === selection.providerId);
    const family = state.generationCatalog?.families.find((item) => item.id === model?.family_id);
    modelPill.innerHTML = model ? modelFamilyBrandMarkHtml(family?.id || "", "studio-model-mark") : "";
    const name = element("span", "studio-model-name", model?.display_name || translate("modelSelection.catalogUnavailable"));
    const via = element("span", "studio-model-provider", provider?.name || translate("modelSelection.providerUnavailable"));
    const caret = element("span", "studio-pill-caret");
    caret.setAttribute("aria-hidden", "true");
    modelPill.append(name, via, caret);
    modelPill.classList.toggle("is-unavailable", !provider);
    modelPill.title = translate("studio.switchModel");
    if (!/Mac|iPhone|iPad/.test(navigator.platform)) runButton.title = runButton.title.replace("Cmd", "Ctrl");

    const openTarget = parameterPills.querySelector<HTMLElement>('[aria-expanded="true"]')?.dataset.studioTarget;
    parameterPills.replaceChildren(...studioPillSpecs(model, selection.parameters).map((spec) => {
      const pill = element("button", `studio-pill${spec.target === "more" ? " studio-more-pill" : ""}${spec.changed ? " is-changed" : ""}`);
      pill.type = "button";
      pill.dataset.studioTarget = spec.target;
      pill.setAttribute("aria-expanded", String(spec.target === openTarget && document.body.hasAttribute("data-studio-params-open")));
      if (spec.label) pill.append(element("span", "studio-pill-label", spec.label));
      pill.append(element("span", "studio-pill-value", spec.value));
      pill.addEventListener("click", () => openParams(spec.target, pill));
      return pill;
    }));
  };

  const renderModelMenu = () => {
    const { state } = getLegacyBridge();
    const catalog = state.generationCatalog;
    modelMenu.replaceChildren();
    if (!catalog) return;
    const operation = state.mode as GenerationOperation;
    catalog.families.forEach((family) => {
      const rows = catalog.models
        .filter((model) => model.family_id === family.id)
        .flatMap((model) => eligibleProviderBindings(catalog, model.id, operation).map((entry) => ({ model, entry })));
      if (!rows.length) return;
      const group = element("div", "studio-model-group");
      const heading = element("div", "studio-model-group-heading");
      heading.innerHTML = modelFamilyBrandMarkHtml(family.id, "studio-model-mark");
      heading.append(element("span", "", family.display_name));
      group.append(heading);
      rows.forEach(({ model, entry }) => {
        const selected = model.id === state.selectedModelId
          && entry.provider.id === state.selectedProviderId
          && entry.binding.id === state.selectedProviderBindingId;
        const row = element("button", `studio-model-option${selected ? " is-selected" : ""}`);
        row.type = "button";
        row.setAttribute("aria-pressed", String(selected));
        row.append(element("span", "studio-model-option-name", model.display_name), element("span", "studio-model-option-provider", bindingLabel(entry)));
        row.addEventListener("click", () => {
          state.lastProviderByModel[model.id] = entry.provider.id;
          state.lastProviderSelectionByModel[model.id] = entry.selectionKey;
          if (model.id !== state.selectedModelId) selectConcreteModel(model.id);
          else selectGenerationProvider(entry.selectionKey);
          closeModelMenu();
          renderPills();
        });
        group.append(row);
      });
      modelMenu.append(group);
    });
    if (!modelMenu.children.length) {
      modelMenu.append(element("p", "studio-model-empty", translate("modelSelection.providerUnavailable")));
    }
    const manage = element("button", "ghost-button studio-model-manage", translate("studio.manageProviders"));
    manage.type = "button";
    manage.addEventListener("click", () => {
      closeModelMenu();
      document.getElementById("generationProviderSettingsButton")?.click();
    });
    modelMenu.append(manage);
  };

  const toggleModelMenu = () => {
    if (!modelMenu.hidden) {
      closeModelMenu();
      return;
    }
    closeParams();
    recipes.close();
    renderModelMenu();
    modelMenu.hidden = false;
    modelPill.setAttribute("aria-expanded", "true");
    modelMenu.querySelector<HTMLElement>(".is-selected, .studio-model-option")?.focus({ preventScroll: true });
  };

  const apply = () => {
    const next = query.matches;
    if (next === active) return;
    active = next;
    document.body.toggleAttribute("data-studio", active);
    if (active) {
      promptCompose.after(bar);
      controls.append(modelMenu, recipes.menu);
      runButton.before(runMarker);
      runSlot.append(runButton);
      renderPills();
    } else {
      closeParams();
      closeModelMenu();
      recipes.close();
      runMarker.replaceWith(runButton);
      bar.remove();
      modelMenu.remove();
      recipes.menu.remove();
    }
  };

  modelPill.addEventListener("click", toggleModelMenu);
  document.addEventListener("pointerdown", (event) => {
    const target = event.target as Node | null;
    if (!target || !active) return;
    if (!modelMenu.hidden && !modelMenu.contains(target) && !modelPill.contains(target)) closeModelMenu();
    if (!recipes.menu.hidden && !recipes.menu.contains(target) && !recipes.button.contains(target)) recipes.close();
    if (document.body.hasAttribute("data-studio-params-open")
      && !outputPanel.contains(target) && !parameterPills.contains(target)
      && !(target as Element).closest?.(".themed-select-menu, .model-combobox-options, [role='listbox']")) {
      closeParams();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (!active) return;
    if (event.key === "Escape") {
      if (!modelMenu.hidden) { closeModelMenu(); modelPill.focus(); event.stopPropagation(); }
      else if (!recipes.menu.hidden) { recipes.close(); recipes.button.focus(); event.stopPropagation(); }
      else if (document.body.hasAttribute("data-studio-params-open")) { closeParams(); event.stopPropagation(); }
      return;
    }
    if (event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "m") {
      event.preventDefault();
      toggleModelMenu();
    }
  }, true);

  // A timer rather than requestAnimationFrame: frames pause in hidden tabs,
  // and the pills must reflect the catalog as soon as it loads.
  let pending = 0;
  const schedule = () => {
    if (!active) return;
    window.clearTimeout(pending);
    pending = window.setTimeout(renderPills, 0);
  };
  // The execution summary is rewritten after every model, provider or parameter change.
  new MutationObserver(schedule).observe(summary, { attributes: true, childList: true, characterData: true, subtree: true });
  document.addEventListener(LOCALE_CHANGE_EVENT, schedule);
  query.addEventListener("change", apply);
  apply();
}
