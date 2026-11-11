import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(dirname(fileURLToPath(import.meta.url)))

function read(relativePath: string): string {
  return readFileSync(join(root, relativePath), 'utf8')
}

function readPublic(name: string): string {
  return read(join('public', name))
}

describe('PWA manifest', () => {
  it('is valid JSON with required fields', () => {
    const manifest = JSON.parse(readPublic('manifest.webmanifest'))

    expect(typeof manifest.name).toBe('string')
    expect(manifest.name.length).toBeGreaterThan(0)
    expect(manifest.start_url).toBe('/')
    expect(manifest.display).toBe('standalone')
    expect(Array.isArray(manifest.icons)).toBe(true)
    expect(manifest.icons.length).toBeGreaterThanOrEqual(1)
  })

  it('uses the dark theme colors and Thai language', () => {
    const manifest = JSON.parse(readPublic('manifest.webmanifest'))

    expect(manifest.theme_color.toLowerCase()).toBe('#070b14')
    expect(manifest.background_color.toLowerCase()).toBe('#070b14')
    expect(manifest.lang).toBe('th')
    expect(manifest.scope).toBe('/')
  })
})

describe('index.html', () => {
  const html = read('index.html')

  it('links the web manifest', () => {
    expect(html).toContain('rel="manifest"')
    expect(html).toContain('/manifest.webmanifest')
  })

  it('declares theme-color and apple touch icon', () => {
    expect(html).toContain('name="theme-color"')
    expect(html).toContain('#070b14')
    expect(html).toContain('rel="apple-touch-icon"')
    expect(html).toContain('/icon.svg')
  })

  it('does not reference a missing favicon file', () => {
    expect(html).not.toContain('/favicon.svg')
  })
})

describe('responsive styles', () => {
  const app = read('src/App.vue')

  it('has a small-screen breakpoint', () => {
    expect(app).toContain('@media (max-width: 640px)')
    expect(app).toContain('@media (max-width: 900px)')
  })

  it('collapses the grid to one column on phones', () => {
    const phoneBlock = app.slice(app.indexOf('@media (max-width: 640px)'))
    expect(phoneBlock).toContain('grid-template-columns: 1fr')
  })

  it('renders the sidebar shell with the theme toggle', () => {
    expect(app).toContain('--sidebar-w')
    expect(app).toContain('class="sidebar"')
    expect(app).toContain('data-testid="theme-toggle"')
  })
})

type Listener = (event: unknown) => void

interface FakeRequestInit {
  method?: string
  mode?: string
  headers?: Record<string, string>
}

interface Harness {
  listeners: Record<string, Listener>
  cacheMatch: ReturnType<typeof vi.fn>
  cachePut: ReturnType<typeof vi.fn>
  cacheOpen: ReturnType<typeof vi.fn>
  self: {
    skipWaiting: ReturnType<typeof vi.fn>
    clients: { claim: ReturnType<typeof vi.fn> }
  }
}

const originalSelf = Object.getOwnPropertyDescriptor(globalThis, 'self')
let harness: Harness | null = null

function fakeRequest(url: string, init: FakeRequestInit = {}) {
  const headers = new Map(
    Object.entries(init.headers ?? {}).map(([key, value]) => [key.toLowerCase(), value])
  )
  return {
    url,
    method: init.method ?? 'GET',
    mode: init.mode ?? 'cors',
    headers: {
      get: (name: string) => headers.get(name.toLowerCase()) ?? null,
    },
  }
}

function loadServiceWorker(): Harness {
  const listeners: Record<string, Listener> = {}
  const cacheMatch = vi.fn(async () => undefined)
  const cachePut = vi.fn(async () => undefined)
  const cacheOpen = vi.fn(async () => ({ match: cacheMatch, put: cachePut }))

  const cachesFake = {
    open: cacheOpen,
    keys: vi.fn(async () => ['windy-shell-v2', 'windy-v1']),
    delete: vi.fn(async () => true),
    match: vi.fn(async () => undefined),
  }

  const selfFake = {
    addEventListener: (type: string, fn: Listener) => {
      listeners[type] = fn
    },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn(async () => undefined) },
    location: { origin: 'http://localhost' },
  }

  Object.defineProperty(globalThis, 'self', {
    value: selfFake,
    configurable: true,
    writable: true,
  })
  vi.stubGlobal('caches', cachesFake)

  new Function(readPublic('sw.js'))()

  harness = { listeners, cacheMatch, cachePut, cacheOpen, self: selfFake }
  return harness
}

function dispatchFetch(request: ReturnType<typeof fakeRequest>) {
  const current = harness
  if (!current) throw new Error('service worker not loaded')
  const respondWith = vi.fn()
  const waitUntil = vi.fn()
  current.listeners.fetch({ request, respondWith, waitUntil })
  return respondWith
}

function shellResponse(type = 'basic'): Response {
  const response = new Response('<!doctype html><div id="app"></div>', {
    headers: { 'content-type': 'text/html' },
  })
  Object.defineProperty(response, 'type', { value: type })
  return response
}

afterEach(() => {
  vi.unstubAllGlobals()
  if (originalSelf) {
    Object.defineProperty(globalThis, 'self', originalSelf)
  }
  harness = null
})

describe('service worker routing', () => {
  it('never touches caches or network for /api requests', async () => {
    const h = loadServiceWorker()
    const respondWith = dispatchFetch(fakeRequest('http://localhost/api/system'))

    expect(respondWith).not.toHaveBeenCalled()
    expect(h.cacheOpen).not.toHaveBeenCalled()
    expect(h.cacheMatch).not.toHaveBeenCalled()
  })

  it('never touches caches or network for /ws requests', () => {
    const h = loadServiceWorker()
    const respondWith = dispatchFetch(fakeRequest('http://localhost/ws/telemetry'))

    expect(respondWith).not.toHaveBeenCalled()
    expect(h.cacheOpen).not.toHaveBeenCalled()
  })

  it('bypasses cross-origin, non-GET and malformed URLs', () => {
    const h = loadServiceWorker()

    expect(dispatchFetch(fakeRequest('http://elsewhere.test/app.js'))).not.toHaveBeenCalled()
    expect(dispatchFetch(fakeRequest('http://localhost/app.js', { method: 'POST' }))).not.toHaveBeenCalled()
    expect(h.cacheOpen).not.toHaveBeenCalled()
  })

  it('uses network-first for navigation requests even when a stale shell is cached', async () => {
    const fresh = shellResponse()
    const stale = shellResponse()
    const fetchMock = vi.fn(async () => fresh)
    vi.stubGlobal('fetch', fetchMock)

    const h = loadServiceWorker()
    h.cacheMatch.mockResolvedValue(stale)

    const respondWith = dispatchFetch(fakeRequest('http://localhost/security', { mode: 'navigate' }))

    expect(respondWith).toHaveBeenCalledTimes(1)
    const response = await respondWith.mock.calls[0][0]

    expect(response).toBe(fresh)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('treats an Accept: text/html request as navigation (network-first)', async () => {
    const fresh = shellResponse()
    const fetchMock = vi.fn(async () => fresh)
    vi.stubGlobal('fetch', fetchMock)

    loadServiceWorker()

    const respondWith = dispatchFetch(
      fakeRequest('http://localhost/maintenance', { headers: { accept: 'text/html,*/*' } })
    )
    const response = await respondWith.mock.calls[0][0]

    expect(response).toBe(fresh)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('falls back to the cached shell when the navigation network call fails', async () => {
    const stale = shellResponse()
    const fetchMock = vi.fn(async () => {
      throw new Error('offline')
    })
    vi.stubGlobal('fetch', fetchMock)

    const h = loadServiceWorker()
    h.cacheMatch.mockImplementation(async (key: unknown) =>
      key === '/index.html' ? stale : undefined
    )

    const respondWith = dispatchFetch(fakeRequest('http://localhost/security', { mode: 'navigate' }))
    const response = await respondWith.mock.calls[0][0]

    expect(response).toBe(stale)
    expect(h.cacheMatch).toHaveBeenCalledWith('/index.html')
  })

  it('refreshes the cached shell after a successful navigation', async () => {
    const fresh = shellResponse()
    vi.stubGlobal('fetch', vi.fn(async () => fresh))

    const h = loadServiceWorker()

    const respondWith = dispatchFetch(fakeRequest('http://localhost/', { mode: 'navigate' }))
    await respondWith.mock.calls[0][0]

    expect(h.cachePut).toHaveBeenCalledWith('/index.html', expect.anything())
  })

  it('serves static assets from cache while revalidating in the background', async () => {
    const cached = new Response('asset')
    const fresh = new Response('asset-v2')
    const fetchMock = vi.fn(async () => fresh)
    vi.stubGlobal('fetch', fetchMock)

    const h = loadServiceWorker()
    h.cacheMatch.mockResolvedValue(cached)

    const respondWith = dispatchFetch(
      fakeRequest('http://localhost/assets/app.js', { headers: { accept: '*/*' } })
    )
    const response = await respondWith.mock.calls[0][0]

    expect(response).toBe(cached)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('falls through to the network for an uncached static asset', async () => {
    const fresh = new Response('asset')
    vi.stubGlobal('fetch', vi.fn(async () => fresh))

    loadServiceWorker()

    const respondWith = dispatchFetch(
      fakeRequest('http://localhost/assets/app.css', { headers: { accept: 'text/css' } })
    )
    const response = await respondWith.mock.calls[0][0]

    expect(response).toBe(fresh)
  })

  it('installs with skipWaiting and a versioned shell cache', () => {
    const h = loadServiceWorker()
    const waitUntil = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async () => shellResponse()))

    h.listeners.install({ waitUntil })

    expect(waitUntil).toHaveBeenCalledTimes(1)
    expect(h.self.skipWaiting).toHaveBeenCalled()
  })

  it('activates with clients.claim and drops caches from other versions', async () => {
    const h = loadServiceWorker()
    const waitUntil = vi.fn()

    h.listeners.activate({ waitUntil })
    await waitUntil.mock.calls[0][0]

    expect(h.self.clients.claim).toHaveBeenCalled()
  })
})

describe('service worker source', () => {
  const sw = readPublic('sw.js')

  it('documents the network-first navigation strategy', () => {
    expect(sw).toContain("request.mode === 'navigate'")
    expect(sw.toLowerCase()).toContain('network-first')
  })

  it('version-binds the cache name and warns about bumping it', () => {
    expect(sw).toContain("const CACHE_VERSION = 'v2'")
    expect(sw).toContain("const CACHE = 'windy-shell-' + CACHE_VERSION")
    expect(sw.toUpperCase()).toContain('BUMP CACHE_VERSION')
  })

  it('bypasses api and ws and does not load scripts from a CDN', () => {
    expect(sw).toContain('/api')
    expect(sw).toContain('/ws')
    expect(sw).not.toContain("importScripts('https")
  })
})
