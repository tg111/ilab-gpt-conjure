/**
 * Provider-level model discovery: one "获取可用模型" call lists what the
 * provider serves, recognised models are matched to catalog models, and the
 * checked ones become bindings in one step instead of one form row each.
 */
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import {
  BINDING_TEMPLATES,
  availableProtocolsForModel,
  bindingTemplateForProtocol,
  protocolForBinding,
  type BindingProtocol,
  type BindingTemplateId,
} from "./provider-model-bindings";
import { fetchProviderModels, type ModelDiscoveryConnection } from "./provider-model-discovery";
import type { CatalogModel, ProviderModelBindingSettings } from "./types";

export interface DiscoveredChoice {
  remote: string;
  modelId: string;
}

/** Native Gemini endpoints list models their own way; everything else is OpenAI-style. */
export function discoveryProtocolForBaseUrl(baseUrl: string): BindingProtocol {
  try {
    const url = new URL(baseUrl);
    const path = url.pathname.replace(/\/+$/, "");
    if (path.endsWith("/openai")) return "openai_images";
    if (path.endsWith("/v1beta") || url.hostname === "generativelanguage.googleapis.com") return "gemini";
  } catch {
    // Incomplete URLs fall back to the common case.
  }
  return "openai_images";
}

/**
 * Matches a provider's model id to a catalog model by its id or official id,
 * allowing vendor prefixes ("google/…") and suffixes ("…-preview", "…:free").
 * The longest key wins, so "nano-banana-2-lite" is not read as "nano-banana-2".
 */
export function matchCatalogModel(remoteId: string, models: readonly CatalogModel[]): string {
  const id = String(remoteId || "").trim().toLowerCase().split("/").pop() || "";
  let best = "";
  let bestLength = 0;
  for (const model of models) {
    if (!availableProtocolsForModel(model.id).length) continue;
    for (const raw of [model.id, model.official_model_id]) {
      const key = String(raw || "").toLowerCase();
      if (!key || key.length <= bestLength) continue;
      if (id === key || (id.startsWith(key) && /[-:@_]/.test(id.charAt(key.length)))) {
        best = model.id;
        bestLength = key.length;
      }
    }
  }
  return best;
}

function family(modelId: string): string {
  return modelId.startsWith("nano-banana") ? "nano-banana" : "gpt-image";
}

/**
 * The protocol a new binding should use: copy what this provider already uses
 * for the same model family, else go by the base URL.
 */
export function templateForDiscoveredModel(
  modelId: string,
  baseUrl: string,
  bindings: readonly ProviderModelBindingSettings[],
): BindingTemplateId {
  const protocols = availableProtocolsForModel(modelId);
  const sibling = bindings.find((binding) => family(binding.canonical_model_id) === family(modelId)
    && protocols.includes(protocolForBinding(binding)));
  if (sibling) {
    const match = (Object.keys(BINDING_TEMPLATES) as BindingTemplateId[]).find((id) => (
      BINDING_TEMPLATES[id].protocol_profile === sibling.protocol_profile
      && BINDING_TEMPLATES[id].parameter_codec === sibling.parameter_codec
    ));
    if (match) return match;
  }
  const preferred = discoveryProtocolForBaseUrl(baseUrl);
  return bindingTemplateForProtocol(modelId, protocols.includes(preferred) ? preferred : protocols[0]!);
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = "", text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function initProviderDiscoveryPanel(context: {
  button: HTMLButtonElement | null;
  status: HTMLElement | null;
  results: HTMLElement | null;
  connectionInputs: Array<HTMLInputElement | null>;
  getConnection(): ModelDiscoveryConnection;
  getModels(): CatalogModel[];
  getBindings(): ProviderModelBindingSettings[];
  addChoices(choices: DiscoveredChoice[]): number;
}): { clear(): void } {
  const { button, status, results } = context;
  if (!button || !status || !results) return { clear() {} };
  let controller: AbortController | null = null;

  const setStatus = (message: string, error = false) => {
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle("error", error);
  };
  const setBusy = (busy: boolean) => {
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
    button.textContent = translate(busy ? "apiSettings.fetchingModels" : "apiSettings.discoverModels");
  };
  const clear = () => {
    controller?.abort();
    controller = null;
    setBusy(false);
    setStatus("");
    results.hidden = true;
    results.replaceChildren();
  };

  const selectedCount = () => results.querySelectorAll<HTMLInputElement>("input[data-discovery-remote]:checked:not(:disabled)").length;
  const syncAddButton = () => {
    const add = results.querySelector<HTMLButtonElement>("[data-discovery-add]");
    if (!add) return;
    const count = selectedCount();
    add.disabled = count === 0;
    add.textContent = formatTranslation("apiSettings.discoveryAddSelected", { count: String(count) });
  };

  const modelName = (modelId: string) => context.getModels().find((model) => model.id === modelId)?.display_name || modelId;

  const item = (remote: string, modelId: string, bindings: ProviderModelBindingSettings[], models: CatalogModel[]) => {
    // Unmatched rows hold a select, which must not toggle the checkbox as a label would.
    const row: HTMLElement = modelId ? el("label", "provider-discovery-item") : el("div", "provider-discovery-item");
    row.dataset.discoveryText = remote.toLowerCase();
    const checkbox = el("input");
    checkbox.type = "checkbox";
    checkbox.dataset.discoveryRemote = remote;
    checkbox.dataset.discoveryModel = modelId;
    row.append(checkbox, el("code", "provider-discovery-remote", remote));
    if (modelId) {
      const existing = bindings.find((binding) => binding.canonical_model_id === modelId);
      const target = el("span", "provider-discovery-target", modelName(modelId));
      if (existing?.remote_model_id === remote) {
        checkbox.checked = true;
        checkbox.disabled = true;
        target.textContent = `${modelName(modelId)} · ${translate("apiSettings.discoveryAdded")}`;
      } else if (existing) {
        target.textContent = `${modelName(modelId)} · ${translate("apiSettings.discoveryReplaces")}`;
        target.title = existing.remote_model_id;
      }
      row.append(target);
    } else {
      const select = el("select", "control provider-discovery-model");
      select.append(new Option(translate("apiSettings.discoveryChooseModel"), ""));
      models.filter((model) => availableProtocolsForModel(model.id).length)
        .forEach((model) => select.append(new Option(model.display_name, model.id)));
      select.addEventListener("change", () => {
        checkbox.dataset.discoveryModel = select.value;
        checkbox.checked = Boolean(select.value);
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
      });
      row.append(select);
    }
    return row;
  };

  const render = (remotes: string[]) => {
    const models = context.getModels();
    const bindings = context.getBindings();
    const matched = remotes.map((remote) => ({ remote, modelId: matchCatalogModel(remote, models) }));
    const known = matched.filter((entry) => entry.modelId);
    const others = matched.filter((entry) => !entry.modelId);
    results.replaceChildren();
    if (remotes.length > 12) {
      const filter = el("input", "control provider-discovery-filter");
      filter.type = "search";
      filter.placeholder = translate("apiSettings.discoveryFilter");
      filter.setAttribute("aria-label", translate("apiSettings.discoveryFilter"));
      filter.addEventListener("input", () => {
        const query = filter.value.trim().toLowerCase();
        results.querySelectorAll<HTMLElement>("[data-discovery-text]").forEach((row) => {
          row.hidden = Boolean(query) && !row.dataset.discoveryText!.includes(query);
        });
        if (query && others.length) results.querySelector("details")?.setAttribute("open", "");
      });
      results.append(filter);
    }
    if (known.length) {
      const list = el("div", "provider-discovery-list");
      // Pre-check one recognised name per model the provider does not serve yet.
      const claimed = new Set(bindings.map((binding) => binding.canonical_model_id));
      known.forEach((entry) => {
        const row = item(entry.remote, entry.modelId, bindings, models);
        const checkbox = row.querySelector<HTMLInputElement>("input[data-discovery-remote]");
        if (checkbox && !checkbox.disabled && !claimed.has(entry.modelId)) {
          checkbox.checked = true;
          claimed.add(entry.modelId);
        }
        list.append(row);
      });
      results.append(list);
    }
    if (others.length) {
      const details = el("details", "provider-discovery-others");
      if (!known.length) details.open = true;
      details.append(el("summary", "", formatTranslation("apiSettings.discoveryOthers", { count: String(others.length) })));
      const list = el("div", "provider-discovery-list");
      others.forEach((entry) => list.append(item(entry.remote, "", bindings, models)));
      details.append(list);
      results.append(details);
    }
    const footer = el("div", "provider-discovery-footer");
    const add = el("button", "run-button provider-discovery-add");
    add.type = "button";
    add.dataset.discoveryAdd = "";
    const close = el("button", "ghost-button", translate("apiSettings.discoveryClose"));
    close.type = "button";
    close.addEventListener("click", clear);
    footer.append(close, add);
    results.append(footer);
    results.hidden = false;
    syncAddButton();
    setStatus(known.length
      ? formatTranslation("apiSettings.discoverySummary", { count: String(remotes.length), matched: String(known.length) })
      : formatTranslation("apiSettings.discoveryNoMatch", { count: String(remotes.length) }));
  };

  results.addEventListener("change", (event) => {
    const checkbox = event.target as HTMLInputElement | null;
    if (!checkbox?.matches("input[data-discovery-remote]")) return;
    // One provider model per catalog model: a binding per model and operation.
    if (checkbox.checked && checkbox.dataset.discoveryModel) {
      results.querySelectorAll<HTMLInputElement>("input[data-discovery-remote]:checked:not(:disabled)").forEach((other) => {
        if (other !== checkbox && other.dataset.discoveryModel === checkbox.dataset.discoveryModel) other.checked = false;
      });
    }
    if (checkbox.checked && !checkbox.dataset.discoveryModel) {
      checkbox.checked = false;
      checkbox.parentElement?.querySelector<HTMLSelectElement>("select")?.focus();
    }
    syncAddButton();
  });
  results.addEventListener("click", (event) => {
    const add = (event.target as HTMLElement | null)?.closest<HTMLButtonElement>("[data-discovery-add]");
    if (!add || add.disabled) return;
    const choices = [...results.querySelectorAll<HTMLInputElement>("input[data-discovery-remote]:checked:not(:disabled)")]
      .map((checkbox) => ({ remote: checkbox.dataset.discoveryRemote || "", modelId: checkbox.dataset.discoveryModel || "" }))
      .filter((choice) => choice.remote && choice.modelId);
    const count = context.addChoices(choices);
    clear();
    if (count) setStatus(formatTranslation("apiSettings.discoveryApplied", { count: String(count) }));
  });

  button.addEventListener("click", async () => {
    if (button.disabled) return;
    clear();
    const current = new AbortController();
    controller = current;
    setBusy(true);
    setStatus(translate("apiSettings.fetchingModels"));
    const connection = context.getConnection();
    try {
      const remotes = await fetchProviderModels(connection, discoveryProtocolForBaseUrl(connection.base_url), current.signal);
      if (controller !== current) return;
      if (!remotes.length) {
        setStatus(translate("apiSettings.modelsEmpty"));
        return;
      }
      render(remotes);
    } catch (error) {
      if (controller !== current || current.signal.aborted) return;
      const key = error instanceof Error && error.message.startsWith("apiSettings.")
        ? error.message : "apiSettings.modelsFetchFailed";
      setStatus(translate(key), true);
    } finally {
      if (controller === current) {
        controller = null;
        setBusy(false);
      }
    }
  });
  // Results describe one URL and key; editing either makes them stale.
  context.connectionInputs.forEach((input) => input?.addEventListener("input", clear));
  document.addEventListener(LOCALE_CHANGE_EVENT, clear);
  return { clear };
}
