// Service worker for the Tuttie wallet PWA: lets it be installed on the home screen and open
// offline. Network first, so a deployed change shows up on the next load; the cache is only a
// fallback when the phone is offline.
const CACHE = "tuttie-wallet-v1";
const SHELL = [
  "/wallet/", "/wallet/manifest.json", "/wallet/icons/icon-192.png",
  "/shared/tuttie.css", "/shared/face.js",
];

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
  const appFile = url.pathname.startsWith("/wallet/") || url.pathname.startsWith("/shared/");
  if (request.method !== "GET" || url.origin !== location.origin || !appFile) return;
  event.respondWith(
    fetch(request)
      .then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(request, copy));
        return response;
      })
      .catch(() => caches.match(request)));
});
