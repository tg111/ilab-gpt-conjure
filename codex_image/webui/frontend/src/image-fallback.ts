// Small previews load a server-side thumbnail first and fall back to the
// original image only if the thumbnail cannot be served.

const FALLBACK_ATTRIBUTE = "data-fallback-src";
let installed = false;

export function thumbnailFirstUrl(item: any): string {
  if (!item) return "";
  return String(item.thumbnail_url || item.image_url || item.previewUrl || "");
}

function fallbackFor(primaryUrl: string, fullUrl: unknown): string {
  const clean = String(fullUrl || "");
  return clean && clean !== primaryUrl ? clean : "";
}

/** Attribute string for HTML templates; callers escape the value. */
export function thumbnailFallbackAttribute(item: any, escape: (value: string) => string): string {
  const fallback = fallbackFor(thumbnailFirstUrl(item), item?.image_url);
  return fallback ? ` ${FALLBACK_ATTRIBUTE}="${escape(fallback)}"` : "";
}

const TASK_MEDIA_IMAGE_URL = /^(\/api\/tasks\/[^/?#]+\/(?:outputs|inputs)\/[1-9]\d*)\/image$/i;

/** Maps a stored task image URL to its thumbnail route; other URLs are returned unchanged. */
export function taskMediaThumbnailUrl(url: unknown): string {
  const clean = String(url || "").trim();
  const match = TASK_MEDIA_IMAGE_URL.exec(clean);
  return match ? `${match[1]}/thumbnail` : clean;
}

/** `src` plus fallback attributes for an image whose stored URL may be a full-size task image. */
export function taskMediaThumbnailAttributes(url: unknown, escape: (value: string) => string): string {
  const full = String(url || "").trim();
  return `src="${escape(taskMediaThumbnailUrl(full))}"${thumbnailFallbackAttribute({ thumbnail_url: taskMediaThumbnailUrl(full), image_url: full }, escape)}`;
}

export function setThumbnailFirstSource(image: HTMLImageElement, item: any): void {
  const primary = thumbnailFirstUrl(item);
  const fallback = fallbackFor(primary, item?.image_url);
  if (fallback) image.setAttribute(FALLBACK_ATTRIBUTE, fallback);
  else image.removeAttribute(FALLBACK_ATTRIBUTE);
  image.src = primary;
}

export function installThumbnailFallback(): void {
  if (installed || typeof document === "undefined") return;
  installed = true;
  // Image errors do not bubble, so listen in the capture phase.
  document.addEventListener("error", (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement)) return;
    const fallback = image.getAttribute(FALLBACK_ATTRIBUTE);
    if (!fallback) return;
    image.removeAttribute(FALLBACK_ATTRIBUTE);
    image.src = fallback;
  }, true);
}
