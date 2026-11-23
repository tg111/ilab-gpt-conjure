import { formatTranslation, translate } from "./i18n";
import { getLegacyBridge } from "./state";
import type { CatalogCustomSizeRules, CatalogModel } from "./types";

const SIZE_PATTERN = /^(\d+)x(\d+)$/;

/** Translation keys for the backend's custom size error codes. */
const CUSTOM_SIZE_ERROR_KEYS: Readonly<Record<string, string>> = {
  custom_size_invalid_format: "output.customSizeRequired",
  custom_size_out_of_bounds: "output.customSizeBounds",
  custom_size_not_multiple: "output.customSizeMultiple",
  custom_size_ratio_too_large: "output.customSizeRatio",
  custom_size_pixels_out_of_range: "output.customSizePixels",
};

export function parsePixelSize(value: unknown): { width: number; height: number } | null {
  const match = typeof value === "string" ? value.trim().match(SIZE_PATTERN) : null;
  return match ? { width: Number(match[1]), height: Number(match[2]) } : null;
}

/** Frontend twin of the backend's custom_size_error; "" when the size is accepted. */
export function customSizeError(rules: CatalogCustomSizeRules, size: unknown, outputFormat: unknown): string {
  const dimensions = parsePixelSize(size);
  if (!dimensions) return "custom_size_invalid_format";
  const { width, height } = dimensions;
  if (width < rules.min_edge || width > rules.max_edge || height < rules.min_edge || height > rules.max_edge) {
    return "custom_size_out_of_bounds";
  }
  if (width % rules.multiple || height % rules.multiple) return "custom_size_not_multiple";
  if (rules.relaxed_formats.includes(String(outputFormat))) return "";
  if (Math.max(width, height) / Math.min(width, height) > rules.max_aspect_ratio) return "custom_size_ratio_too_large";
  if (width * height < rules.min_pixels || width * height > rules.max_pixels) return "custom_size_pixels_out_of_range";
  return "";
}

export function customSizeErrorMessage(code: string): string {
  return code ? translate(CUSTOM_SIZE_ERROR_KEYS[code] || "modelParameters.invalidValue") : "";
}

/** The legal size closest to the requested ratio first and pixel count second. */
export function suggestLegalSize(
  rules: CatalogCustomSizeRules,
  width: number,
  height: number,
): { width: number; height: number } {
  const step = rules.multiple;
  const w = Number.isFinite(width) && width > 0 ? width : 1024;
  const h = Number.isFinite(height) && height > 0 ? height : 1024;
  const ratio = Math.min(rules.max_aspect_ratio, Math.max(1 / rules.max_aspect_ratio, w / h));
  const pixels = Math.min(rules.max_pixels, Math.max(rules.min_pixels, w * h));
  let best = { width: 1024, height: 1024, score: Infinity };
  const first = Math.ceil(rules.min_edge / step) * step;
  for (let x = first; x <= rules.max_edge; x += step) {
    const low = Math.ceil(Math.max(rules.min_edge, x / rules.max_aspect_ratio, rules.min_pixels / x) / step) * step;
    const high = Math.floor(Math.min(rules.max_edge, x * rules.max_aspect_ratio, rules.max_pixels / x) / step) * step;
    for (let y = low; y <= high; y += step) {
      const score = 8 * Math.abs(Math.log((x / y) / ratio)) + Math.abs(Math.log((x * y) / pixels));
      if (score < best.score) best = { width: x, height: y, score };
    }
  }
  return { width: best.width, height: best.height };
}

/** The pixels requested by unified size parameters: "auto", "WxH", or "" when the provider decides. */
export function requestedSize(model: CatalogModel | undefined, parameters: Record<string, unknown>): string {
  const mode = parameters["canvas.mode"];
  if (mode === "auto") return "auto";
  if (mode === "custom") return String(parameters["canvas.size"] || "");
  const pixels = model?.size_spec?.presets?.[String(parameters["canvas.resolution"])]?.[String(parameters["canvas.aspect_ratio"])];
  return pixels ? `${pixels[0]}x${pixels[1]}` : "";
}

/** Total decoded pixels the server accepts for one GIF (raster_validation.MAX_RASTER_TOTAL_FRAME_PIXELS). */
export const GIF_FRAME_PIXEL_BUDGET = 128 * 1024 * 1024;

/**
 * The most GIF frames allowed for the requested canvas: the catalog maximum,
 * the server's decoded-pixel budget, and a provider's edit limit, never below 2.
 * Null when nothing narrows the catalog maximum.
 */
export function gifFrameLimit(
  model: CatalogModel,
  maximum: number | null,
  values: Record<string, unknown>,
  providerLimit: number | null,
): number | null {
  const limits = [maximum, providerLimit].filter((limit): limit is number => typeof limit === "number");
  const pixels = parsePixelSize(requestedSize(model, values));
  if (pixels) limits.push(Math.floor(GIF_FRAME_PIXEL_BUDGET / (pixels.width * pixels.height)));
  return limits.length ? Math.max(2, Math.min(...limits)) : null;
}

function firstReferenceImageUrl(): string {
  const images = getLegacyBridge().state.images;
  const source = (Array.isArray(images) ? images : []).find((item: any) => item && !item.missing
    && (item.kind === "upload" ? item.previewUrl : item.image_url || item.previewUrl));
  if (!source) return "";
  return String(source.kind === "upload" ? source.previewUrl : source.image_url || source.previewUrl);
}

function loadImageDimensions(url: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const width = image.naturalWidth || image.width;
      const height = image.naturalHeight || image.height;
      if (width > 0 && height > 0) resolve({ width, height });
      else reject(new Error(formatTranslation("output.imageSizeUnavailable")));
    };
    image.onerror = () => reject(new Error(formatTranslation("output.imageLoadFailed")));
    image.src = url;
  });
}

/** Enable "use first image" buttons once a reference image is present, and disable them when none is. */
export function refreshFirstImageButtons(): void {
  if (typeof document === "undefined" || typeof document.querySelectorAll !== "function") return;
  const available = Boolean(firstReferenceImageUrl());
  document.querySelectorAll<HTMLButtonElement>(".pixel-size-from-image").forEach((button) => {
    button.disabled = button.dataset.readOnly === "true" || !available;
  });
}

export interface PixelSizeEditorOptions {
  label: string;
  value: unknown;
  rules: CatalogCustomSizeRules;
  outputFormat: unknown;
  readOnly: boolean;
  commit: (value: string) => void;
  reportError: (message: string) => void;
}

/** Width × height inputs with swap, optional ratio lock, first-image ratio and a legal-size suggestion. */
export function createPixelSizeEditor(options: PixelSizeEditorOptions): HTMLElement {
  const { rules } = options;
  const initial = parsePixelSize(options.value) || { width: 1024, height: 1024 };
  const editor = document.createElement("div");
  editor.className = "pixel-size-editor";
  const row = document.createElement("div");
  row.className = "pixel-size-inputs";
  const input = (labelKey: string, value: number) => {
    const element = document.createElement("input");
    element.type = "number";
    element.className = "control pixel-size-input";
    element.min = String(rules.min_edge);
    element.max = String(rules.max_edge);
    element.step = String(rules.multiple);
    element.inputMode = "numeric";
    element.value = String(value);
    element.setAttribute("aria-label", translate(labelKey));
    element.disabled = options.readOnly;
    return element;
  };
  const width = input("output.width", initial.width);
  const height = input("output.height", initial.height);
  const times = document.createElement("span");
  times.className = "pixel-size-times";
  times.textContent = "×";
  times.setAttribute("aria-hidden", "true");
  const swap = document.createElement("button");
  swap.type = "button";
  swap.className = "ghost-button pixel-size-swap";
  swap.textContent = "⇄";
  swap.title = translate("output.swapSize");
  swap.setAttribute("aria-label", translate("output.swapSize"));
  swap.disabled = options.readOnly;
  row.append(width, times, height, swap);

  const tools = document.createElement("div");
  tools.className = "pixel-size-tools";
  const lockLabel = document.createElement("label");
  lockLabel.className = "pixel-size-lock";
  const lock = document.createElement("input");
  lock.type = "checkbox";
  lock.disabled = options.readOnly;
  const lockText = document.createElement("span");
  lockText.textContent = translate("output.ratioLock");
  lockLabel.append(lock, lockText);
  const fromImage = document.createElement("button");
  fromImage.type = "button";
  fromImage.className = "ghost-button text-sm pixel-size-from-image";
  fromImage.textContent = translate("output.useFirstImage");
  fromImage.title = translate("output.firstImageRatio");
  fromImage.dataset.readOnly = String(options.readOnly);
  fromImage.disabled = options.readOnly || !firstReferenceImageUrl();
  tools.append(lockLabel, fromImage);

  const hint = document.createElement("p");
  hint.className = "pixel-size-hint";
  hint.textContent = translate("output.customSizeHint");
  const error = document.createElement("p");
  error.className = "model-parameter-error hidden";
  error.setAttribute("role", "alert");
  const suggest = document.createElement("button");
  suggest.type = "button";
  suggest.className = "ghost-button text-sm pixel-size-suggest hidden";

  let lockedRatio = initial.width / initial.height;
  const current = () => `${Math.round(Number(width.value))}x${Math.round(Number(height.value))}`;
  const validate = (): string => {
    const code = customSizeError(rules, current(), options.outputFormat);
    const message = customSizeErrorMessage(code);
    error.textContent = message;
    error.classList.toggle("hidden", !message);
    width.setAttribute("aria-invalid", message ? "true" : "false");
    height.setAttribute("aria-invalid", message ? "true" : "false");
    if (message) {
      const suggestion = suggestLegalSize(rules, Number(width.value), Number(height.value));
      suggest.textContent = formatTranslation("output.useSuggestedSize", { size: `${suggestion.width} × ${suggestion.height}` });
      suggest.dataset.size = `${suggestion.width}x${suggestion.height}`;
    }
    suggest.classList.toggle("hidden", !message);
    options.reportError(message);
    if (!message && current() !== options.value) options.commit(current());
    return message;
  };
  const snap = (value: number) => Math.max(rules.min_edge, Math.round(value / rules.multiple) * rules.multiple);
  const set = (next: { width: number; height: number }) => {
    width.value = String(next.width);
    height.value = String(next.height);
    lockedRatio = next.width / next.height;
    validate();
  };
  width.addEventListener("input", () => {
    if (lock.checked && Number(width.value) > 0) height.value = String(snap(Number(width.value) / lockedRatio));
    validate();
  });
  height.addEventListener("input", () => {
    if (lock.checked && Number(height.value) > 0) width.value = String(snap(Number(height.value) * lockedRatio));
    validate();
  });
  lock.addEventListener("change", () => {
    if (Number(width.value) > 0 && Number(height.value) > 0) lockedRatio = Number(width.value) / Number(height.value);
  });
  swap.addEventListener("click", () => set({ width: Number(height.value), height: Number(width.value) }));
  suggest.addEventListener("click", () => {
    const size = parsePixelSize(suggest.dataset.size);
    if (size) set(size);
  });
  fromImage.addEventListener("click", async () => {
    const url = firstReferenceImageUrl();
    if (!url) return;
    try {
      const image = await loadImageDimensions(url);
      const pixels = Number(width.value) * Number(height.value) || 1024 * 1024;
      const scale = Math.sqrt(pixels / (image.width * image.height));
      set(suggestLegalSize(rules, image.width * scale, image.height * scale));
    } catch (failure) {
      error.textContent = failure instanceof Error ? failure.message : String(failure);
      error.classList.remove("hidden");
    }
  });
  editor.append(row, tools, hint, error, suggest);
  // Report the initial state so an invalid stored size blocks submission.
  if (!options.readOnly) queueMicrotask(validate);
  return editor;
}
