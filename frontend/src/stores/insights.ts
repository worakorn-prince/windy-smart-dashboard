import { defineStore } from 'pinia'
import { ref } from 'vue'

export type InsightsRange = '24h' | '7d' | '30d'

export const INSIGHTS_RANGES: InsightsRange[] = ['24h', '7d', '30d']

export const TREND_METRICS = [
  'cpu_pct', 'ram_pct', 'swap_pct', 'cpu_temp', 'gpu_temp', 'disk_temp_max',
  'cpu_power_w', 'gpu_power_w', 'net_sent_bps', 'net_recv_bps',
  'disk_read_bps', 'disk_write_bps',
] as const

export type TrendMetric = (typeof TREND_METRICS)[number]

export type NullableMetric = Record<TrendMetric, number | null>

export interface TrendPoint extends NullableMetric {
  ts: number
}

export interface EffectiveWindow {
  start: number
  end: number
  n: number
}

export interface TrendSeries {
  range: string
  bucket_sec: number
  count: number
  points: TrendPoint[]
}

export interface DiskUsageRow {
  mount: string
  used_gb: number | null
  total_gb: number | null
  first_used_gb: number | null
  avg_used_gb: number | null
  peak_used_gb: number | null
  delta_gb: number | null
  n: number
  first_ts: string
  last_ts: string
}

export interface TopProcessRow {
  name: string
  avg_cpu_pct: number | null
  peak_mem_mb: number | null
  n: number
}

export interface MaintenanceActionRow {
  action: string
  count: number
  ok: number
  failed: number
  success_rate: number | null
}

export interface MaintenanceSummary {
  total: number
  ok: number
  failed: number
  success_rate: number | null
  by_action: MaintenanceActionRow[]
}

export interface SecurityKindRow {
  kind: string
  count: number
}

export interface SecuritySourceRow {
  source_ip: string
  count: number
}

export interface SecuritySummary {
  total: number
  by_kind: SecurityKindRow[]
  top_sources: SecuritySourceRow[]
}

export interface BaselineBand {
  mode: 'flat' | 'hourly'
  hours: Record<string, unknown>
  n: number
  mean: number | null
  std: number | null
  lo: number | null
  hi: number | null
}

export type BaselineProfile = Record<string, BaselineBand>

export interface AnomalyRow {
  metric: string
  ts: number
  value: number
  expected: number | null
  z: number
  direction: 'high' | 'low'
  run_len: number
}

export interface InsightsData {
  range: InsightsRange
  generated_at: string
  effective_window: EffectiveWindow | null
  trends: TrendSeries
  disk: DiskUsageRow[]
  top_processes: TopProcessRow[]
  maintenance: MaintenanceSummary
  security: SecuritySummary
  baseline: BaselineProfile
  anomalies: AnomalyRow[]
}

export const EMPTY_MAINTENANCE: MaintenanceSummary = {
  total: 0, ok: 0, failed: 0, success_rate: null, by_action: [],
}

export const EMPTY_SECURITY: SecuritySummary = {
  total: 0, by_kind: [], top_sources: [],
}

export const EMPTY_TRENDS: TrendSeries = {
  range: '24h', bucket_sec: 0, count: 0, points: [],
}

function asNumber(value: unknown): number | null {
  if (value == null) return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function asList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function normalizeTrends(raw: unknown): TrendSeries {
  const obj = (raw ?? {}) as Record<string, unknown>
  const rawPoints = asList<Record<string, unknown>>(obj.points)
  const points: TrendPoint[] = rawPoints.map((p) => {
    const point = {} as NullableMetric
    for (const metric of TREND_METRICS) point[metric] = asNumber(p[metric])
    return { ts: asNumber(p.ts) ?? 0, ...point }
  })
  return {
    range: typeof obj.range === 'string' ? obj.range : '24h',
    bucket_sec: asNumber(obj.bucket_sec) ?? 0,
    count: asNumber(obj.count) ?? points.length,
    points,
  }
}

export function normalizeInsights(raw: unknown): InsightsData {
  const obj = (raw ?? {}) as Record<string, unknown>
  const windowRaw = obj.effective_window as Record<string, unknown> | null | undefined
  const effectiveWindow = windowRaw
    ? {
        start: asNumber(windowRaw.start) ?? 0,
        end: asNumber(windowRaw.end) ?? 0,
        n: asNumber(windowRaw.n) ?? 0,
      }
    : null
  const maintRaw = (obj.maintenance ?? {}) as Record<string, unknown>
  const maintActions = asList<Record<string, unknown>>(maintRaw.by_action).map((a) => ({
    action: String(a.action ?? '—'),
    count: asNumber(a.count) ?? 0,
    ok: asNumber(a.ok) ?? 0,
    failed: asNumber(a.failed) ?? 0,
    success_rate: asNumber(a.success_rate),
  }))
  const secRaw = (obj.security ?? {}) as Record<string, unknown>
  const anomalies = asList<Record<string, unknown>>(obj.anomalies).map((a) => ({
    metric: String(a.metric ?? '—'),
    ts: asNumber(a.ts) ?? 0,
    value: asNumber(a.value) ?? 0,
    expected: asNumber(a.expected),
    z: asNumber(a.z) ?? 0,
    direction: a.direction === 'low' || a.direction === 'down' ? 'low' as const : 'high' as const,
    run_len: asNumber(a.run_len) ?? 0,
  }))
  const baselineRaw = (obj.baseline ?? {}) as Record<string, Record<string, unknown>>
  const baseline: BaselineProfile = {}
  for (const [metric, profile] of Object.entries(baselineRaw)) {
    baseline[metric] = {
      mode: profile?.mode === 'hourly' ? 'hourly' : 'flat',
      hours: (profile?.hours ?? {}) as Record<string, unknown>,
      n: asNumber(profile?.n) ?? 0,
      mean: asNumber(profile?.mean),
      std: asNumber(profile?.std),
      lo: asNumber(profile?.lo),
      hi: asNumber(profile?.hi),
    }
  }
  return {
    range: (INSIGHTS_RANGES as string[]).includes(String(obj.range)) ? obj.range as InsightsRange : '24h',
    generated_at: typeof obj.generated_at === 'string' ? obj.generated_at : '',
    effective_window: effectiveWindow,
    trends: normalizeTrends(obj.trends),
    disk: asList<Record<string, unknown>>(obj.disk).map((d) => ({
      mount: String(d.mount ?? '—'),
      used_gb: asNumber(d.used_gb),
      total_gb: asNumber(d.total_gb),
      first_used_gb: asNumber(d.first_used_gb),
      avg_used_gb: asNumber(d.avg_used_gb),
      peak_used_gb: asNumber(d.peak_used_gb),
      delta_gb: asNumber(d.delta_gb),
      n: asNumber(d.n) ?? 0,
      first_ts: typeof d.first_ts === 'string' ? d.first_ts : '',
      last_ts: typeof d.last_ts === 'string' ? d.last_ts : '',
    })),
    top_processes: asList<Record<string, unknown>>(obj.top_processes).map((p) => ({
      name: String(p.name ?? '—'),
      avg_cpu_pct: asNumber(p.avg_cpu_pct),
      peak_mem_mb: asNumber(p.peak_mem_mb),
      n: asNumber(p.n) ?? 0,
    })),
    maintenance: {
      total: asNumber(maintRaw.total) ?? 0,
      ok: asNumber(maintRaw.ok) ?? 0,
      failed: asNumber(maintRaw.failed) ?? 0,
      success_rate: asNumber(maintRaw.success_rate),
      by_action: maintActions,
    },
    security: {
      total: asNumber(secRaw.total) ?? 0,
      by_kind: asList<Record<string, unknown>>(secRaw.by_kind).map((k) => ({
        kind: String(k.kind ?? '—'),
        count: asNumber(k.count) ?? 0,
      })),
      top_sources: asList<Record<string, unknown>>(secRaw.top_sources).map((s) => ({
        source_ip: String(s.source_ip ?? '—'),
        count: asNumber(s.count) ?? 0,
      })),
    },
    baseline,
    anomalies,
  }
}

export const useInsightsStore = defineStore('insights', () => {
  const range = ref<InsightsRange>('24h')
  const data = ref<InsightsData | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(r?: InsightsRange) {
    if (r) range.value = r
    loading.value = true
    error.value = null
    try {
      const res = await window.fetch(`/api/insights?range=${range.value}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const raw = await res.json()
      data.value = normalizeInsights(raw)
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  return { range, data, loading, error, load }
})
