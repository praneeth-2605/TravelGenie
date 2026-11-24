/* TravelGenie service worker: makes the app installable and keeps saved trips
   readable offline.

   - App shell (pages, JS, CSS, icons): cached so the app opens without internet.
   - Trip data (GET /api/trips…, /api/auth/me, /api/settings): network first, so it's
     always fresh online; the last copy is used when offline.
   - Everything else (planning, chat, uploads, other sites): network only.
   - The page clears the trip-data cache on logout (message "clear-user-data"). */

const VERSION = 'v1'
const SHELL = `tg-shell-${VERSION}`
const DATA = 'tg-data'
const SHELL_URLS = ['/', '/index.html', '/manifest.webmanifest', '/favicon.svg', '/icon-192.png', '/icon-512.png']
const DATA_PATHS = [/^\/api\/trips(\/[^/]+)?$/, /^\/api\/auth\/me$/, /^\/api\/settings$/]

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_URLS)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('tg-shell-') && k !== SHELL).map(k => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('message', event => {
  if (event.data === 'clear-user-data') event.waitUntil(caches.delete(DATA))
})

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName)
  try {
    const response = await fetch(request)
    if (response.ok) cache.put(request, response.clone())
    return response
  } catch {
    const cached = await cache.match(request)
    if (cached) return cached
    throw new Error('offline')
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) (await caches.open(SHELL)).put(request, response.clone())
  return response
}

self.addEventListener('fetch', event => {
  const { request } = event
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // Saved trips: fresh when online, last copy when offline.
  if (DATA_PATHS.some(re => re.test(url.pathname))) {
    event.respondWith(networkFirst(request, DATA))
    return
  }
  if (url.pathname.startsWith('/api/')) return

  // Page loads: the app shell (the React app handles the route).
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then(r => {
        caches.open(SHELL).then(c => c.put('/index.html', r.clone()))
        return r
      }).catch(async () => (await caches.match('/index.html')) || (await caches.match('/'))),
    )
    return
  }

  // Built assets have content hashes in their names, so a cached copy is always right.
  if (url.pathname.startsWith('/assets/') || SHELL_URLS.includes(url.pathname)) {
    event.respondWith(cacheFirst(request))
  }
})
