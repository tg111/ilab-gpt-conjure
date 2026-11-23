const CACHE_NAME = "ilab-conjure-shell-v412";
const APP_SHELL_URLS = [
  "/",
  "/history",
  "/manifest.webmanifest",
  "/static/styles.css?v=runtime-931",
  "/static/app.js?v=runtime-918",
  "/static/history.js?v=history-199",
  "/static/pwa.js?v=pwa-1",
  "/static/appearance-bootstrap.js?v=2",
  "/static/icons/ui.svg?v=1",
  "/static/image-editor-fill-worker.js?v=1",
  "/static/brand/favicon.svg",
  "/static/brand/pwa-icon-192.png",
  "/static/brand/pwa-icon-512.png"
];
const APP_SHELL_PATHS = new Set(APP_SHELL_URLS.map((url) => new URL(url, self.location.origin).pathname));

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const requestUrl = new URL(request.url);
  if (requestUrl.origin !== self.location.origin) return;
  // Serve custom colors online and use the cached base manifest offline.
  if (requestUrl.pathname === "/manifest.webmanifest" && requestUrl.search) {
    event.respondWith(fetch(request).catch(async () => (
      (await caches.match("/manifest.webmanifest")) || Response.error()
    )));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/", { ignoreSearch: true }))
    );
    return;
  }

  if (!APP_SHELL_PATHS.has(requestUrl.pathname)) return;

  // Network first: the WebUI is served locally, so always prefer the live
  // assets and only fall back to the cache when the server is unreachable.
  // A cache-first strategy kept serving a stale app.js whenever a rebuild
  // forgot to bump the ?v= query, which broke the output settings panel
  // until a hard refresh bypassed the worker.
  event.respondWith(
    fetch(request).then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
      }
      return response;
    }).catch(() => caches.match(request).then((cached) => (
      cached || caches.match(request, { ignoreSearch: true })
    )))
  );
});
