const CACHE = "pcparts-static-v2";
const ASSETS = ["/", "/static/manifest.json", "/static/icons/icon-192.png", "/static/icons/icon-512.png"];
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).catch(()=>{}));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Never serve dynamic data (prices, status, history) from cache.
  if (url.pathname.startsWith("/api/") || url.pathname === "/deals" || url.pathname === "/search") {
    e.respondWith(fetch(req).catch(() => caches.match(req)));
    return;
  }
  // Static assets: cache first, then network.
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(req).then(cached => cached || fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(req, copy));
      return res;
    })));
    return;
  }
  // Pages: network first, fall back to cache (offline support).
  e.respondWith(fetch(req).then(res => {
    const copy = res.clone();
    caches.open(CACHE).then(c => c.put(req, copy));
    return res;
  }).catch(() => caches.match(req)));
});