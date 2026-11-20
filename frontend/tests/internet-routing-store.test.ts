import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useInternetStore } from '@/stores/internet'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

const ROUTES_FIXTURE = {
  routes: [
    { destination: '0.0.0.0', prefix_length: 0, next_hop: '192.168.1.1', interface_index: 12, metric: 25, protocol: 2, age: 3600, origin: 1, is_default: true },
    { destination: '192.168.1.0', prefix_length: 24, next_hop: null, interface_index: 12, metric: 25, protocol: 2, age: 3600, origin: 1, is_default: false },
    { destination: '10.0.0.0', prefix_length: 8, next_hop: '10.0.0.1', interface_index: 13, metric: 10, protocol: 12, age: 1800, origin: 3, is_default: false },
    { destination: '172.16.0.0', prefix_length: 12, next_hop: '172.16.0.1', interface_index: 14, metric: 20, protocol: 13, age: 7200, origin: 1, is_default: false },
  ],
  default_gateway: '192.168.1.1',
  gateway_interface_index: 12,
  snapshot_ts: Date.now() / 1000,
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 300, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const TRACEROUTE_FIXTURE = {
  session_id: 'tr-abc123',
  target: '8.8.8.8',
  max_hops: 30,
  protocol: 'icmp',
  hops: [
    { hop: 1, address: '192.168.1.1', rtt_ms: 1.2, status: 'success' },
    { hop: 2, address: '10.0.0.1', rtt_ms: 2.5, status: 'success' },
    { hop: 3, address: '100.64.0.1', rtt_ms: 8.3, status: 'success' },
    { hop: 4, address: null, rtt_ms: null, status: 'timeout' },
    { hop: 5, address: '8.8.8.8', rtt_ms: 12.7, status: 'success' },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 60, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const ROUTES_HISTORY_FIXTURE = {
  range: '1h',
  changes: [
    { timestamp: Date.now() / 1000 - 300, change_type: 'added', details: { destination: '10.10.0.0/16', next_hop: '10.10.0.1' }, severity: 'medium' },
    { timestamp: Date.now() / 1000 - 600, change_type: 'removed', details: { destination: '172.16.0.0/12' }, severity: 'high' },
    { timestamp: Date.now() / 1000 - 900, change_type: 'changed', details: { destination: '192.168.1.0/24', old_metric: 25, new_metric: 20 }, severity: 'low' },
    { timestamp: Date.now() / 1000 - 1200, change_type: 'updated', details: { destination: '0.0.0.0/0', old_gateway: '192.168.1.254', new_gateway: '192.168.1.1' }, severity: 'critical' },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 3600, end: Date.now() / 1000 },
  source: 'storage',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

describe('internet store — loadRoutes', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads routes data and populates store', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, ROUTES_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadRoutes()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/routes')
    expect(store.routes).toEqual(ROUTES_FIXTURE)
    expect(store.error).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('handles HTTP error', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(500, { detail: 'Internal error' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadRoutes()

    expect(store.error).toContain('500')
    expect(store.routes).toBeNull()
    expect(store.loading).toBe(false)
  })
})

describe('internet store — loadTraceroute', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads traceroute data', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, TRACEROUTE_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadTraceroute('8.8.8.8', 30, 'icmp')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/routes/traceroute?target=8.8.8.8&max_hops=30&protocol=icmp')
    expect(store.traceroute).toEqual(TRACEROUTE_FIXTURE)
    expect(store.loading).toBe(false)
  })

  it('uses custom parameters', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, TRACEROUTE_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadTraceroute('1.1.1.1', 20, 'udp')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/routes/traceroute?target=1.1.1.1&max_hops=20&protocol=udp')
  })

  it('encodes target with special characters', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, TRACEROUTE_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadTraceroute('example.com', 30, 'tcp')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/routes/traceroute?target=example.com&max_hops=30&protocol=tcp')
  })
})

describe('internet store — loadRoutesHistory', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads routes history with default range', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, ROUTES_HISTORY_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadRoutesHistory()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/routes/history?range=1h')
    expect(store.routesHistory).toEqual(ROUTES_HISTORY_FIXTURE)
  })

  it('passes custom range', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { changes: [] }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadRoutesHistory('24h')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/routes/history?range=24h')
  })

  it('handles HTTP error', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(404, { detail: 'Not found' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadRoutesHistory('7d')

    expect(store.error).toContain('404')
    expect(store.routesHistory).toBeNull()
  })
})