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

const DNS_FIXTURE = {
  configured_resolvers: ['1.1.1.1', '8.8.8.8', '9.9.9.9'],
  resolver_health: [
    { resolver: '1.1.1.1', status: 'ok', avg_latency_ms: 15.5, success_rate: 0.99, recent_probes: 100, last_probe_at: Date.now() / 1000 },
    { resolver: '8.8.8.8', status: 'degraded', avg_latency_ms: 45.2, success_rate: 0.95, recent_probes: 100, last_probe_at: Date.now() / 1000 },
    { resolver: '9.9.9.9', status: 'down', avg_latency_ms: null, success_rate: 0.0, recent_probes: 100, last_probe_at: Date.now() / 1000 },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 300, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const DNS_HISTORY_FIXTURE = {
  range: '1h',
  step: 60,
  points: [
    { ts: Date.now() / 1000 - 300, resolver: '1.1.1.1', hostname: 'google.com', record_type: 'A', duration_ms: 12.5, status: 'success', answer_count: 1, error_code: null, probe_method: 'udp' },
    { ts: Date.now() / 1000 - 240, resolver: '1.1.1.1', hostname: 'google.com', record_type: 'A', duration_ms: 14.2, status: 'success', answer_count: 1, error_code: null, probe_method: 'udp' },
    { ts: Date.now() / 1000 - 180, resolver: '8.8.8.8', hostname: 'google.com', record_type: 'A', duration_ms: 38.1, status: 'success', answer_count: 1, error_code: null, probe_method: 'udp' },
    { ts: Date.now() / 1000 - 120, resolver: '8.8.8.8', hostname: 'google.com', record_type: 'A', duration_ms: 42.5, status: 'success', answer_count: 1, error_code: null, probe_method: 'udp' },
    { ts: Date.now() / 1000 - 60, resolver: '9.9.9.9', hostname: 'google.com', record_type: 'A', duration_ms: null, status: 'timeout', answer_count: 0, error_code: 'TIMEOUT', probe_method: 'udp' },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 3600, end: Date.now() / 1000 },
  source: 'storage',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const DNS_COMPARE_FIXTURE = {
  hostname: 'google.com',
  record_type: 'A',
  comparison: [
    { resolver: '1.1.1.1', probe_method: 'udp', duration_ms: 12.3, status: 'success', answer_count: 1, error_code: null },
    { resolver: '8.8.8.8', probe_method: 'udp', duration_ms: 18.7, status: 'success', answer_count: 1, error_code: null },
    { resolver: '9.9.9.9', probe_method: 'udp', duration_ms: null, status: 'timeout', answer_count: 0, error_code: 'TIMEOUT' },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 60, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

describe('internet store — loadDns', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads DNS data and populates store', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, DNS_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadDns()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/dns')
    expect(store.dns).toEqual(DNS_FIXTURE)
    expect(store.error).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('handles HTTP error', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(500, { detail: 'Internal error' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadDns()

    expect(store.error).toContain('500')
    expect(store.dns).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('handles network failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('ECONNREFUSED') }))
    const store = useInternetStore()
    await store.loadDns()
    expect(store.error).toBe('ECONNREFUSED')
  })
})

describe('internet store — loadDnsHistory', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads DNS history with default range', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, DNS_HISTORY_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadDnsHistory()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/dns/history?range=1h&step=60')
    expect(store.dnsHistory).toEqual(DNS_HISTORY_FIXTURE)
  })

  it('passes custom range and step', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { points: [] }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadDnsHistory('24h', 300)

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/dns/history?range=24h&step=300')
  })
})

describe('internet store — loadDnsCompare', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads DNS comparison', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, DNS_COMPARE_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadDnsCompare('google.com', 'A')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/dns/compare?hostname=google.com&record_type=A')
    expect(store.dnsCompare).toEqual(DNS_COMPARE_FIXTURE)
  })

  it('encodes hostname with special characters', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, DNS_COMPARE_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadDnsCompare('example.com', 'AAAA')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/dns/compare?hostname=example.com&record_type=AAAA')
  })

  it('handles HTTP error', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(404, { detail: 'Not found' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadDnsCompare('nonexistent.invalid', 'A')

    expect(store.error).toContain('404')
    expect(store.dnsCompare).toBeNull()
  })
})