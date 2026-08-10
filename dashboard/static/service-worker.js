// RENCORA service worker — app-shell caching for fast, installable PWA.
// This does NOT make the live AI work without a connection (it needs to reach
// your PC), it only makes the shell (HTML/CSS/JS/icons/fonts) load instantly
// and lets the browser install it as a real app icon on your phone.

const CACHE = 'basi-ai-shell-v1';
const SHELL = [
  '/login',
  '/static/crypto.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/favicon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first for everything (this is a live dashboard), falling back to
// cache only when the network is unreachable — so a flaky connection still
// shows *something* instead of a browser error page.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  // Never intercept API calls or websockets
  if (req.url.includes('/api/') || req.url.includes('/ws')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
        return res;
      })
      .catch(() => caches.match(req))
  );
});
