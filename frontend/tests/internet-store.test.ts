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

const OVERVIEW_FIXTURE = {
  connection_status: 'connected',
  internet_quality: {
    primary: {
      target_id: 'primary',
      address: '1.1.1.1',
      probe_type: 'tcp',
      latency_ms: { min: 10, median: 15, p95: 25, max: 50, count: 100, timeouts: 0 },
      jitter_ms: 2.5,
      loss_pct: 0.0,
      status: 'success',
      last_probe_at: Date.now() / 1000,
    },
    secondary: {
      target_id: 'secondary',
      address: '8.8.8.8',
      probe_type: 'tcp',
      latency_ms: { min: 12, median: 18, p95: 30, max: 55, count: 100, timeouts: 1 },
      jitter_ms: 3.2,
      loss_pct: 1.0,
      status: 'success',
      last_probe_at: Date.now() / 1000,
    },
    gateway: {
      target_id: 'gateway',
      address: '192.168.1.1',
      probe_type: 'tcp',
      latency_ms: { min: 1, median: 2, p95: 5, max: 10, count: 100, timeouts: 0 },
      jitter_ms: 0.5,
      loss_pct: 0.0,
      status: 'success',
      last_probe_at: Date.now() / 1000,
    },
  },
  current_throughput: { send_bps: 1_000_000, recv_bps: 5_000_000, interface_id: 'eth0' },
  active_interface: {
    id: 'eth0',
    name: 'Ethernet',
    description: 'Intel Ethernet',
    mac: '00:11:22:33:44:55',
    type: 'Ethernet',
    speed_mbps: 1000,
    status: 'up',
    connection_name: 'Ethernet',
    manufacturer: 'Intel',
    ipv4: ['192.168.1.100'],
    ipv6: [],
    gateway: ['192.168.1.1'],
    dns: ['1.1.1.1', '8.8.8.8'],
    current_rates: { send_bps: 1_000_000, recv_bps: 5_000_000 },
    errors: { in: 0, out: 0, discards_in: 0, discards_out: 0 },
  },
  recent_incidents: [
    { id: 'inc1', started_at: Date.now() / 1000 - 300, category: 'quality', severity: 'medium', title: 'Latency spike detected' },
  ],
  dns_health: { configured: ['1.1.1.1', '8.8.8.8'], primary_status: 'ok', secondary_status: 'ok' },
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 300, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const QUALITY_FIXTURE = {
  targets: [
    {
      target_id: 'gateway',
      address: '192.168.1.1',
      probe_type: 'tcp',
      latency_ms: { min: 1, median: 2, p95: 5, max: 10, count: 100, timeouts: 0 },
      jitter_ms: 0.5,
      loss_pct: 0.0,
      status: 'success',
      last_probe_at: Date.now() / 1000,
    },
    {
      target_id: 'primary',
      address: '1.1.1.1',
      probe_type: 'tcp',
      latency_ms: { min: 10, median: 15, p95: 25, max: 50, count: 100, timeouts: 0 },
      jitter_ms: 2.5,
      loss_pct: 0.0,
      status: 'success',
      last_probe_at: Date.now() / 1000,
    },
    {
      target_id: 'secondary',
      address: '8.8.8.8',
      probe_type: 'tcp',
      latency_ms: { min: 12, median: 18, p95: 30, max: 55, count: 100, timeouts: 1 },
      jitter_ms: 3.2,
      loss_pct: 1.0,
      status: 'success',
      last_probe_at: Date.now() / 1000,
    },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 300, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const INTERFACES_FIXTURE = {
  interfaces: [
    {
      id: 'eth0',
      name: 'Ethernet',
      description: 'Intel Ethernet',
      mac: '00:11:22:33:44:55',
      type: 'Ethernet',
      speed_mbps: 1000,
      status: 'up',
      connection_name: 'Ethernet',
      manufacturer: 'Intel',
      ipv4: ['192.168.1.100'],
      ipv6: [],
      gateway: ['192.168.1.1'],
      dns: ['1.1.1.1', '8.8.8.8'],
      current_rates: { send_bps: 1_000_000, recv_bps: 5_000_000 },
      errors: { in: 0, out: 0, discards_in: 0, discards_out: 0 },
    },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 300, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

describe('internet store — loadOverview', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads overview and populates store', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, OVERVIEW_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadOverview()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/overview')
    expect(store.overview).toEqual(OVERVIEW_FIXTURE)
    expect(store.error).toBeNull()
    expect(store.loading).toBe(false)
    expect(store.isConnected).toBe(true)
    expect(store.isDegraded).toBe(false)
  })

  it('handles degraded connection status', async () => {
    const degradedFixture = { ...OVERVIEW_FIXTURE, connection_status: 'degraded' as const }
    const fetchMock = vi.fn(async () => jsonResponse(200, degradedFixture))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadOverview()

    expect(store.isConnected).toBe(false)
    expect(store.isDegraded).toBe(true)
  })

  it('maps HTTP error to error state', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(500, { detail: 'Internal error' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadOverview()

    expect(store.error).toContain('500')
    expect(store.overview).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('maps network failure to error message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('ECONNREFUSED') }))
    const store = useInternetStore()
    await store.loadOverview()
    expect(store.error).toBe('ECONNREFUSED')
  })
})

describe('internet store — loadQuality', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads quality data and computes derived values', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, QUALITY_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadQuality()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/quality')
    expect(store.quality).toEqual(QUALITY_FIXTURE)
    expect(store.primaryLatency).toBe(15)
    expect(store.primaryLoss).toBe(0)
    expect(store.gatewayLatency).toBe(2)
  })
})

describe('internet store — loadInterfaces', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads interfaces data', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, INTERFACES_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadInterfaces()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/interfaces')
    expect(store.interfaces).toEqual(INTERFACES_FIXTURE)
  })
})

describe('internet store — loadQualityHistory', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads quality history with default range and target', async () => {
    const historyFixture = {
      target_id: 'primary',
      range: '1h',
      points: [{ ts: Date.now() / 1000, target_id: 'primary', probe_type: 'tcp', rtt_ms: 15, status: 'success', error_code: null }],
      generated_at: Date.now() / 1000,
      data_window: { start: Date.now() / 1000 - 3600, end: Date.now() / 1000 },
      source: 'storage',
      status: 'ok',
      errors: [],
      coverage: 1.0,
    }
    const fetchMock = vi.fn(async () => jsonResponse(200, historyFixture))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadQualityHistory()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/quality/history?range=1h&target_id=primary&step=60')
    expect(store.qualityHistory).toEqual(historyFixture)
  })

  it('passes custom range and target_id', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { points: [] }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadQualityHistory('24h', 'gateway')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/quality/history?range=24h&target_id=gateway&step=60')
  })
})

describe('internet store — loadInterfaceHistory', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads interface history', async () => {
    const historyFixture = {
      interface_id: 'eth0',
      range: '1h',
      points: [{ ts: Date.now() / 1000, bytes_sent: 1000, bytes_recv: 2000, send_bps: 100, recv_bps: 200, packets_sent: 10, packets_recv: 20, errors_in: 0, errors_out: 0, discards_in: 0, discards_out: 0, link_status: 'up' }],
      generated_at: Date.now() / 1000,
      data_window: { start: Date.now() / 1000 - 3600, end: Date.now() / 1000 },
      source: 'storage',
      status: 'ok',
      errors: [],
      coverage: 1.0,
    }
    const fetchMock = vi.fn(async () => jsonResponse(200, historyFixture))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadInterfaceHistory('eth0')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/interfaces/eth0/history?range=1h')
    expect(store.interfaceHistory).toEqual(historyFixture)
  })
})

describe('internet store — loadAll', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads overview, quality, and interfaces in parallel', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(200, OVERVIEW_FIXTURE))
      .mockResolvedValueOnce(jsonResponse(200, QUALITY_FIXTURE))
      .mockResolvedValueOnce(jsonResponse(200, INTERFACES_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadAll()

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(store.overview).toEqual(OVERVIEW_FIXTURE)
    expect(store.quality).toEqual(QUALITY_FIXTURE)
    expect(store.interfaces).toEqual(INTERFACES_FIXTURE)
  })
})