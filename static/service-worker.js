/* =========================================================================
   service-worker.js — makes PaperPilot installable + handles push.

   A service worker is a script the browser runs in the background, separate
   from the page. It lets us:
     1. Cache the app shell so it opens instantly and works offline-ish.
     2. Receive Web Push notifications even when the app isn't open.
     3. Focus/open the app when a notification is tapped.

   Bump CACHE_VERSION whenever you change cached files, so browsers fetch fresh.
   ========================================================================= */

const CACHE_VERSION = "papertrail-v12";

// The core files that make up the app "shell".
const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/css/styles.css",
  "/js/app.js",
  "/js/tutor.js",
  "/js/push.js",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

/* ---- Install: pre-cache the shell -------------------------------------- */
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  // Activate this new worker immediately.
  self.skipWaiting();
});

/* ---- Activate: clean up old caches ------------------------------------- */
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

/* ---- Fetch strategy ----------------------------------------------------
   * API calls (/api/...) always go to the network (never cached — they're
     dynamic and often need the server).
   * Everything else: try cache first, fall back to network (and cache it).
   ------------------------------------------------------------------------ */
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API responses.
  if (url.pathname.startsWith("/api/")) {
    return; // let the browser handle it normally (network)
  }

  // Only handle same-origin GET requests with the cache.
  if (event.request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((response) => {
          // Cache a copy of successful responses for next time.
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => cached); // offline and not cached -> undefined is fine
    })
  );
});

/* ---- Push: show a notification ----------------------------------------- */
self.addEventListener("push", (event) => {
  let data = { title: "Paper Trail", body: "Time for a 2-minute paper break?", url: "/" };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch (e) {
    // If the payload isn't JSON, keep the defaults.
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url: data.url || "/" },
      vibrate: [80, 40, 80],
    })
  );
});

/* ---- Notification tap: focus or open the app --------------------------- */
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      // If a window is already open, focus it.
      for (const client of windowClients) {
        if ("focus" in client) return client.focus();
      }
      // Otherwise open a new one.
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
