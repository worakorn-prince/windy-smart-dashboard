// Cache name is tied to the app-shell version.
// MUST bump CACHE_VERSION whenever the app shell changes (index.html, manifest, icons,
// or any bundle filename), otherwise clients can keep serving an outdated shell.
const CACHE_VERSION = 'v2'
const CACHE = 'windy-shell-' + CACHE_VERSION

const PRECACHE = ['/', '/index.html', '/manifest.webmanifest', '/icon.svg']
const NAVIGATION_TIMEOUT = 3000

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      self.skipWaiting()
      const cache = await caches.open(CACHE)
      await Promise.all(
        PRECACHE.map(async (url) => {
          try {
            const res = await fetch(url, { cache: 'reload' })
            if (res && res.ok) await cache.put(url, res.clone())
          } catch (err) {
            // best-effort: a missing precache entry must not fail the whole install
          }
        })
      )
    })()
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys()
      await Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
      await self.clients.claim()
    })()
  )
})

function isBypassed(url) {
  return url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')
}

function isHtmlRequest(request) {
  if (request.mode === 'navigate') return true
  const accept = request.headers && typeof request.headers.get === 'function'
    ? request.headers.get('accept')
    : null
  return typeof accept === 'string' && accept.includes('text/html')
}

function isCacheable(response) {
  return !!response && response.ok && response.type === 'basic'
}

async function cacheShell(cache, response) {
  if (!isCacheable(response)) return
  try {
    await cache.put('/index.html', response.clone())
  } catch (err) {
    // ignore quota / opaque failures
  }
}

// Network-first: an updated shell must always win when the network is available.
// Only falls back to the cached shell when the network fails or is too slow.
async function networkFirst(request, cache) {
  const fallback = async () => {
    const exact = await cache.match(request)
    if (exact) return exact
    const shell = await cache.match('/index.html')
    if (shell) return shell
    return Response.error()
  }

  let timer
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => resolve(null), NAVIGATION_TIMEOUT)
  })

  const network = fetch(request)
    .then(async (response) => {
      await cacheShell(cache, response)
      return response
    })
    .catch(() => null)

  const winner = await Promise.race([network, timeout])
  clearTimeout(timer)
  if (winner) return winner
  return fallback()
}

// Stale-while-revalidate: assets may be served from cache, refreshed in background.
async function staleWhileRevalidate(request, cache) {
  const cached = await cache.match(request)

  const network = fetch(request)
    .then((response) => {
      if (isCacheable(response)) {
        cache.put(request, response.clone()).catch(() => {})
      }
      return response
    })
    .catch(() => null)

  if (cached) return cached

  const fresh = await network
  if (fresh) return fresh
  return Response.error()
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  let url
  try {
    url = new URL(request.url)
  } catch (err) {
    return
  }

  if (url.origin !== self.location.origin) return
  if (isBypassed(url)) return

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE)
      if (isHtmlRequest(request)) return networkFirst(request, cache)
      return staleWhileRevalidate(request, cache)
    })()
  )
})
