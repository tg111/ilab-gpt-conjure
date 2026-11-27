/**
 * Recipes: named snapshots of model + provider + parameters, applied in one
 * click from the studio composer. Stored in this browser only.
 */
import { getLegacyBridge } from "./state";
import { formatTranslation, translate } from "./i18n";
import { currentGenerationSelection } from "./generation-request";
import { selectConcreteModel } from "./model-selection";
import { eligibleProviderBindings, selectGenerationProvider, providerBindingSelectionKey } from "./provider-selection";
import type { GenerationOperation } from "./types";

const STORAGE_KEY = "codex-image-studio-recipes-v1";

export interface StudioRecipe {
  id: string;
  name: string;
  modelId: string;
  providerSelectionKey: string;
  parameters: Record<string, unknown>;
  summary: string;
}

export function parseRecipes(raw: string | null): StudioRecipe[] {
  try {
    const value = JSON.parse(raw || "[]");
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is StudioRecipe => (
      item && typeof item === "object"
      && typeof item.id === "string" && typeof item.name === "string"
      && typeof item.modelId === "string" && typeof item.providerSelectionKey === "string"
      && item.parameters && typeof item.parameters === "object" && !Array.isArray(item.parameters)
    )).map((item) => ({ ...item, summary: typeof item.summary === "string" ? item.summary : "" }));
  } catch {
    return [];
  }
}

function loadRecipes(): StudioRecipe[] {
  try {
    return parseRecipes(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return [];
  }
}

function storeRecipes(recipes: StudioRecipe[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(recipes));
  } catch {
    // Storage full or disabled: the recipe simply isn't kept.
  }
}

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  if (text) node.textContent = text;
  return node;
}

/** Returns false when the recipe's model or provider binding is gone. */
export function applyRecipe(recipe: StudioRecipe): boolean {
  const bridge = getLegacyBridge();
  const { state } = bridge;
  const catalog = state.generationCatalog;
  if (!catalog) return false;
  const entries = eligibleProviderBindings(catalog, recipe.modelId, state.mode as GenerationOperation);
  const entry = entries.find((item) => item.selectionKey === recipe.providerSelectionKey) || entries[0];
  if (!entry) return false;
  state.lastProviderByModel[recipe.modelId] = entry.provider.id;
  state.lastProviderSelectionByModel[recipe.modelId] = entry.selectionKey;
  if (recipe.modelId !== state.selectedModelId) selectConcreteModel(recipe.modelId);
  else selectGenerationProvider(entry.selectionKey);
  // Set after switching: switching models migrates the previous draft over this one.
  state.parameterDraftsByModel[recipe.modelId] = JSON.parse(JSON.stringify(recipe.parameters));
  bridge.methods.persistModelSelection?.();
  bridge.methods.renderCurrentModelParameters?.();
  bridge.methods.updateRequestPreview?.();
  return true;
}

export interface StudioRecipeControls {
  button: HTMLButtonElement;
  menu: HTMLDivElement;
  close: () => void;
  toggle: () => void;
}

export function createStudioRecipes(describeCurrent: () => string, onBeforeOpen: () => void): StudioRecipeControls {
  const button = element("button", "studio-pill studio-recipe-pill");
  button.type = "button";
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", "studioRecipeMenu");
  button.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M6 3h12v18l-6-4-6 4z"/></svg>';
  const label = element("span", "studio-pill-value");
  button.append(label);

  const menu = element("div", "studio-popover studio-recipe-menu");
  menu.id = "studioRecipeMenu";
  menu.setAttribute("role", "dialog");
  menu.hidden = true;

  const close = () => {
    menu.hidden = true;
    button.setAttribute("aria-expanded", "false");
  };

  const render = () => {
    label.textContent = translate("studio.recipes");
    menu.setAttribute("aria-label", translate("studio.recipes"));
    menu.replaceChildren();
    const recipes = loadRecipes();
    const list = element("div", "studio-recipe-list");
    if (!recipes.length) list.append(element("p", "studio-recipe-empty", translate("studio.recipeEmpty")));
    recipes.forEach((recipe) => {
      const row = element("div", "studio-recipe-row");
      const apply = element("button", "studio-recipe-apply");
      apply.type = "button";
      apply.append(element("span", "studio-recipe-name", recipe.name), element("span", "studio-recipe-summary", recipe.summary));
      apply.addEventListener("click", () => {
        if (applyRecipe(recipe)) {
          close();
          return;
        }
        apply.classList.add("is-unavailable");
        apply.title = translate("studio.recipeUnavailable");
        getLegacyBridge().methods.setStatus?.(translate("studio.recipeUnavailable"), "error");
      });
      const remove = element("button", "ghost-button studio-recipe-remove");
      remove.type = "button";
      remove.title = translate("studio.recipeDelete");
      remove.setAttribute("aria-label", formatTranslation("studio.recipeDeleteNamed", { name: recipe.name }));
      remove.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="/static/icons/ui.svg?v=1#close"/></svg>';
      remove.addEventListener("click", () => {
        storeRecipes(loadRecipes().filter((item) => item.id !== recipe.id));
        render();
      });
      row.append(apply, remove);
      list.append(row);
    });

    const form = element("form", "studio-recipe-form");
    const input = element("input", "control studio-recipe-input");
    input.type = "text";
    input.maxLength = 40;
    input.placeholder = translate("studio.recipeNamePlaceholder");
    input.setAttribute("aria-label", translate("studio.recipeNamePlaceholder"));
    const save = element("button", "ghost-button studio-recipe-save", translate("studio.recipeSave"));
    save.type = "submit";
    form.append(input, save);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const name = input.value.trim();
      const { state } = getLegacyBridge();
      const selection = currentGenerationSelection();
      if (!name || !selection.canonicalModelId || !state.selectedProviderId) {
        input.focus();
        return;
      }
      const recipe: StudioRecipe = {
        id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
        name,
        modelId: selection.canonicalModelId,
        providerSelectionKey: providerBindingSelectionKey(state.selectedProviderId, selection.bindingId),
        parameters: JSON.parse(JSON.stringify(state.parameterDraftsByModel[selection.canonicalModelId] || {})),
        summary: describeCurrent(),
      };
      // Same name replaces the older recipe so saving again updates it.
      storeRecipes([recipe, ...loadRecipes().filter((item) => item.name !== name)]);
      render();
    });

    menu.append(list, form);
  };

  const toggle = () => {
    if (!menu.hidden) {
      close();
      return;
    }
    onBeforeOpen();
    render();
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
    menu.querySelector<HTMLElement>(".studio-recipe-apply, .studio-recipe-input")?.focus({ preventScroll: true });
  };

  button.addEventListener("click", toggle);
  render();
  return { button, menu, close, toggle };
}
