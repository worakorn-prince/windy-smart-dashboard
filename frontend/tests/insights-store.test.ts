import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { EMPTY_INSIGHTS_FIXTURE, INSIGHTS_FIXTURE } from './insights-fixtures'
import {
  normalizeInsights,
  useInsightsStore,
  type InsightsData,
} from '@/stores/insights'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response
}

describe('insights store — load', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads default 24h range and stores normalized payload', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, INSIGHTS_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInsightsStore()
    await store.load()

    expect(fetchMock).toHaveBeenCalledWith('/api/insights?range=24h')
    expect(store.range).toBe('24h')
    expect(store.error).toBeNull()
    expect(store.loading).toBe(false)
    expect(store.data).not.toBeNull()
    expect(store.data!.effective_window).toEqual({ start: 1_763_500_000, end: 1_763_536_000, n: 1200 })
    expect(store.data!.trends.points).toHaveLength(2)
    expect(store.data!.trends.points[0]!.cpu_pct).toBe(10.5)
    expect(store.data!.disk[0]!.mount).toBe('C:\\')
    expect(store.data!.top_processes[0]!.name).toBe('chrome.exe')
    expect(store.data!.maintenance.success_rate).toBe(0.9)
    expect(store.data!.security.total).toBe(42)
    expect(store.data!.baseline.cpu_pct!.mode).toBe('flat')
    expect(store.data!.anomalies[0]!.direction).toBe('high')
  })

  it('switches range and requests the new range', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { ...INSIGHTS_FIXTURE, range: '7d' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInsightsStore()
    await store.load('7d')

    expect(fetchMock).toHaveBeenLastCalledWith('/api/insights?range=7d')
    expect(store.range).toBe('7d')
  })

  it('maps HTTP 422 to error without losing previous data', async () => {
    const store = useInsightsStore()
    const good = vi.fn(async () => jsonResponse(200, INSIGHTS_FIXTURE))
    vi.stubGlobal('fetch', good)
    await store.load()

    const bad = vi.fn(async () => jsonResponse(422, { detail: 'bad range' }))
    vi.stubGlobal('fetch', bad)
    await store.load('999x' as never)

    expect(store.error).toContain('422')
    expect(store.data).not.toBeNull()
    expect(store.loading).toBe(false)
  })

  it('maps network failure to error message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('ECONNREFUSED')
    }))
    const store = useInsightsStore()
    await store.load()
    expect(store.error).toBe('ECONNREFUSED')
    expect(store.data).toBeNull()
  })
})

describe('insights store — normalizeInsights edge cases', () => {
  it('keeps success_rate null when there is no data (never divides by zero)', () => {
    const data: InsightsData = normalizeInsights(EMPTY_INSIGHTS_FIXTURE)
    expect(data.maintenance.success_rate).toBeNull()
    expect(data.maintenance.total).toBe(0)
    expect(data.maintenance.by_action).toEqual([])
    expect(data.effective_window).toBeNull()
    expect(data.trends.points).toEqual([])
    expect(data.disk).toEqual([])
    expect(data.top_processes).toEqual([])
    expect(data.security).toEqual({ total: 0, by_kind: [], top_sources: [] })
    expect(data.baseline).toEqual({})
    expect(data.anomalies).toEqual([])
  })

  it('fills missing trend metrics with null and coerces bad values', () => {
    const data: InsightsData = normalizeInsights({
      trends: { points: [{ ts: 1_763_500_000, cpu_pct: '11.25' }] },
      maintenance: { total: '5', ok: '4', success_rate: '0.8' },
      security: { total: null },
    })
    const point = data.trends.points[0]!
    expect(point.cpu_pct).toBe(11.25)
    expect(point.ram_pct).toBeNull()
    expect(point.gpu_temp).toBeNull()
    expect(data.maintenance.total).toBe(5)
    expect(data.maintenance.success_rate).toBe(0.8)
    expect(data.security.total).toBe(0)
  })

  it('normalizes anomaly direction and baseline mode', () => {
    const data: InsightsData = normalizeInsights({
      baseline: { swap_pct: { mode: 'weird', lo: 1, hi: 2 } },
      anomalies: [{ metric: 'swap_pct', ts: 1, value: 9, direction: 'down' }],
    })
    expect(data.baseline.swap_pct!.mode).toBe('flat')
    expect(data.anomalies[0]!.direction).toBe('low')
  })
})
