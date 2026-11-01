// Service worker for the Tuttie wallet PWA: lets it be installed on the home screen and open
// offline. Network first, so a deployed change shows up on the next load; the cache is only a
// fallback when the phone is offline.
// Bump CACHE when the cached files must be dropped (e.g. after a change of the app's structure).
const CACHE = "tuttie-wallet-v6";
// The built JS and CSS have hashed names and are cached on first use (see the fetch handler).
const SHELL = ["/wallet/", "/wallet/manifest.json", "/wallet/icons/icon-192.png"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  // Only the app's own files; API calls and the event stream go straight to the network.
  const appFile = url.pathname.startsWith("/wallet/");
  if (request.method !== "GET" || url.origin !== location.origin || !appFile) return;
  event.respondWith(
    // "no-cache": revalidate with the server, never take a stale copy from the HTTP cache.
    fetch(request, { cache: "no-cache" })
      .then(response => {
        if (response.ok) {  // never let an error page (e.g. a 502 during a restart) replace the offline copy
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request)));
});
