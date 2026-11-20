<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useInsightsStore, type TrendMetric, type TrendPoint } from '@/stores/insights'
import { epochSecToDate, formatDateTime, formatWindowSpan } from '@/utils/insights'
import InsightsCardShell from './InsightsCardShell.vue'

const store = useInsightsStore()

interface SeriesDef {
  key: TrendMetric
  label: string
  scale: string
  stroke: string
  div?: number
}

const BYTES_PER_MB = 1024 * 1024
const BAND_LABEL = 'ช่วงปกติ (baseline ±3σ)'
const BAND_STROKE = '#94a3b8'
const BAND_FILL = 'rgba(148, 163, 184, 0.12)'

const SERIES_DEFS: SeriesDef[] = [
  { key: 'cpu_pct', label: 'CPU %', scale: '%', stroke: '#22d3ee' },
  { key: 'ram_pct', label: 'RAM %', scale: '%', stroke: '#a3e635' },
  { key: 'swap_pct', label: 'Swap %', scale: '%', stroke: '#4ade80' },
  { key: 'cpu_temp', label: 'CPU °C', scale: '°C', stroke: '#fbbf24' },
  { key: 'gpu_temp', label: 'GPU °C', scale: '°C', stroke: '#a78bfa' },
  { key: 'disk_temp_max', label: 'Disk °C', scale: '°C', stroke: '#f97316' },
  { key: 'cpu_power_w', label: 'CPU W', scale: 'W', stroke: '#f472b6' },
  { key: 'gpu_power_w', label: 'GPU W', scale: 'W', stroke: '#fb923c' },
  { key: 'net_recv_bps', label: 'Net ↓ MB/s', scale: 'MB/s', stroke: '#38bdf8', div: BYTES_PER_MB },
  { key: 'net_sent_bps', label: 'Net ↑ MB/s', scale: 'MB/s', stroke: '#818cf8', div: BYTES_PER_MB },
  { key: 'disk_read_bps', label: 'Disk R MB/s', scale: 'MB/s', stroke: '#34d399', div: BYTES_PER_MB },
  { key: 'disk_write_bps', label: 'Disk W MB/s', scale: 'MB/s', stroke: '#f87171', div: BYTES_PER_MB },
]

type TabId = 'cpu' | 'ram' | 'gpu' | 'network' | 'disk'

interface TabDef {
  id: TabId
  label: string
  keys: TrendMetric[]
  bandMetric: TrendMetric
}

const TABS: TabDef[] = [
  { id: 'cpu', label: 'CPU', keys: ['cpu_pct', 'cpu_temp', 'cpu_power_w'], bandMetric: 'cpu_pct' },
  { id: 'ram', label: 'RAM', keys: ['ram_pct', 'swap_pct'], bandMetric: 'ram_pct' },
  { id: 'gpu', label: 'GPU', keys: ['gpu_temp', 'gpu_power_w'], bandMetric: 'gpu_temp' },
  { id: 'network', label: 'Network', keys: ['net_recv_bps', 'net_sent_bps'], bandMetric: 'net_recv_bps' },
  { id: 'disk', label: 'Disk', keys: ['disk_read_bps', 'disk_write_bps', 'disk_temp_max'], bandMetric: 'disk_read_bps' },
]

function tabDef(id: TabId): TabDef {
  return TABS.find(t => t.id === id) ?? TABS[0]!
}

const activeTab = ref<TabId>('cpu')
const chartEl = ref<HTMLElement | null>(null)
let uplot: uPlot | null = null
let resizeObs: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null

const points = computed<TrendPoint[]>(() => store.data?.trends.points ?? [])
const ready = computed(() => points.value.length > 0)
const subtitle = computed(() => `คำขอช่วง ${RANGE_LABELS[store.range] ?? store.range}`)
const activeDefs = computed<SeriesDef[]>(() =>
  tabDef(activeTab.value).keys
    .map(key => SERIES_DEFS.find(d => d.key === key))
    .filter((d): d is SeriesDef => d !== undefined))

const band = computed(() => {
  const tab = tabDef(activeTab.value)
  const profile = store.data?.baseline?.[tab.bandMetric]
  if (!profile || profile.lo == null || profile.hi == null) return null
  const def = SERIES_DEFS.find(d => d.key === tab.bandMetric)
  if (!def) return null
  return { def, lo: profile.lo, hi: profile.hi, mode: profile.mode, n: profile.n }
})

const RANGE_LABELS: Record<string, string> = {
  '24h': '24 ชม.',
  '7d': '7 วัน',
  '30d': '30 วัน',
}

const windowNote = computed(() => {
  const w = store.data?.effective_window
  if (!w || !w.n) return null
  const start = epochSecToDate(w.start)
  const end = epochSecToDate(w.end)
  const span = formatWindowSpan(w.start, w.end)
  const startText = start ? formatDateTime(start) : '—'
  const endText = end ? formatDateTime(end) : '—'
  const bucket = store.data?.trends.bucket_sec ?? 0
  const bucketText = bucket > 0 ? ` · bucket ${bucket}s` : ''
  return `ข้อมูลจริง ${span} (${startText} – ${endText}) · ${w.n.toLocaleString()} samples${bucketText}`
})

function fmtVal(def: SeriesDef, v: number | null): string {
  if (v == null) return '-'
  if (def.div) return (v / def.div).toFixed(2)
  return v.toFixed(1)
}

function buildData(): uPlot.AlignedData {
  const pts = points.value
  const x: number[] = pts.map(p => p.ts * 1000)
  const ys: (number | null)[][] = activeDefs.value.map(d =>
    pts.map(p => {
      const v: number | null = p[d.key]
      return v == null ? null : (d.div ? v / d.div : v)
    }))
  const bandArrays: (number | null)[][] = band.value
    ? [
        pts.map(() => band.value!.lo),
        pts.map(() => band.value!.hi),
      ]
    : []
  return [x, ...ys, ...bandArrays]
}

function hexToRgba(hex: string, alpha: number): string {
  const raw = hex.replace('#', '')
  const full = raw.length === 3 ? raw.split('').map(c => c + c).join('') : raw.padEnd(6, '0').slice(0, 6)
  const r = parseInt(full.slice(0, 2), 16) || 0
  const g = parseInt(full.slice(2, 4), 16) || 0
  const b = parseInt(full.slice(4, 6), 16) || 0
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function makeFill(color: string) {
  return (u: uPlot): CanvasGradient => {
    const grad = u.ctx.createLinearGradient(0, u.bbox.top, 0, u.bbox.top + u.bbox.height)
    grad.addColorStop(0, hexToRgba(color, 0.14))
    grad.addColorStop(1, hexToRgba(color, 0))
    return grad
  }
}

function usedScales(defs: SeriesDef[]): string[] {
  const out: string[] = []
  for (const d of defs) if (!out.includes(d.scale)) out.push(d.scale)
  if (band.value && !out.includes(band.value.def.scale)) out.push(band.value.def.scale)
  return out
}

function destroyChart(): void {
  if (uplot) {
    uplot.destroy()
    uplot = null
  }
}

function render(): void {
  destroyChart()
  if (!chartEl.value || !points.value.length) return
  if (resizeObs) resizeObs.observe(chartEl.value)
  const defs = activeDefs.value
  const scales = usedScales(defs)
  const css = getComputedStyle(document.documentElement)
  const cGrid = css.getPropertyValue('--grid-line').trim() || '#16203a'
  const cMuted = css.getPropertyValue('--muted').trim() || '#64748b'

  const axisStyle = {
    stroke: cMuted,
    grid: { stroke: cGrid, width: 1 },
    ticks: { stroke: cGrid, width: 1 },
    font: '11px ui-monospace, monospace',
  }

  const bandSeries = band.value
    ? [
        {
          label: `${BAND_LABEL} (ต่ำ)`,
          scale: band.value.def.scale,
          stroke: 'transparent',
          width: 0,
          value: () => '',
        },
        {
          label: BAND_LABEL,
          scale: band.value.def.scale,
          stroke: hexToRgba(BAND_STROKE, 0.7),
          width: 1,
          dash: [4, 4],
          fill: () => BAND_FILL,
          fillTo: band.value.lo as number,
          value: () => '',
        },
      ]
    : []

  const opts: uPlot.Options = {
    width: chartEl.value.clientWidth || 600,
    height: 300,
    series: [
      {},
      ...defs.map(d => ({
        label: d.label,
        stroke: d.stroke,
        width: 2,
        fill: makeFill(d.stroke),
        scale: d.scale,
        spanGaps: false,
        value: (_u: uPlot, v: number | null) => fmtVal(d, v),
      })),
      ...bandSeries,
    ],
    axes: [{ scale: 'x', ...axisStyle }, ...scales.map(s => ({ scale: s, ...axisStyle }))],
    scales: Object.fromEntries(scales.map(s => [s, { auto: true }])),
    legend: { show: false },
    cursor: { points: { show: false } },
  }

  uplot = new uPlot(opts, buildData(), chartEl.value)
}

function selectTab(id: TabId): void {
  if (id !== activeTab.value) activeTab.value = id
}

onMounted(() => {
  themeObserver = new MutationObserver(() => render())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  resizeObs = new ResizeObserver(() => {
    if (uplot && chartEl.value) {
      uplot.setSize({ width: chartEl.value.clientWidth || 600, height: 300 })
    }
  })
  render()
})

watch([points, activeTab, band, () => store.data?.trends.bucket_sec], () => render(), { flush: 'post' })

onBeforeUnmount(() => {
  if (themeObserver) themeObserver.disconnect()
  if (resizeObs) resizeObs.disconnect()
  destroyChart()
})
</script>

<template>
  <InsightsCardShell
    title="แนวโน้มการใช้งาน (trends)"
    :subtitle="subtitle"
    testid="insights-trends"
    :loading="store.loading"
    :ready="ready"
    :error="store.error"
    :empty="ready ? undefined : 'ยังไม่มีข้อมูล samples'"
    @retry="store.load()"
  >
    <p
      v-if="windowNote"
      class="window-note"
      data-testid="insights-window-note"
      role="status"
    >{{ windowNote }}</p>

    <div class="tabs" data-testid="insights-trend-tabs">
      <button
        v-for="t in TABS"
        :key="t.id"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === t.id }"
        :data-testid="`insights-trend-tab-${t.id}`"
        @click="selectTab(t.id)"
      >{{ t.label }}</button>
    </div>

    <div class="legend">
      <span v-for="d in activeDefs" :key="d.key" class="legend-item">
        <span class="legend-dot" :style="{ background: d.stroke, color: d.stroke }"></span>
        {{ d.label }}
      </span>
      <span v-if="band" class="legend-item band-item">
        <span class="legend-dot band-dot" :style="{ background: 'transparent', borderColor: BAND_STROKE }"></span>
        {{ BAND_LABEL }}
        <span class="band-mode">({{ band.mode === 'hourly' ? 'hourly profile' : 'flat' }})</span>
      </span>
    </div>

    <div ref="chartEl" class="chart"></div>
  </InsightsCardShell>
</template>

<style scoped>
.window-note {
  margin: 8px 0 0;
  padding: 6px 10px;
  border: 1px dashed var(--border);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-ctl);
  color: var(--text-dim);
  font-size: 12px;
  font-family: var(--font-mono, ui-monospace, monospace);
}
.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 2px; }
.tab-btn {
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 12px;
  font-size: 12px;
  cursor: pointer;
}
.tab-btn:hover { color: var(--text); border-color: var(--border-strong); }
.tab-btn.active {
  color: var(--accent);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  font-weight: 600;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-dim);
}
.legend-item { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-mono, ui-monospace, monospace); }
.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
  box-shadow: 0 0 8px currentColor;
}
.band-dot {
  border: 1px dashed currentColor;
  box-shadow: none;
  border-radius: 2px;
}
.band-item { color: var(--muted); }
.band-mode { color: var(--muted); font-size: 11px; }
.chart { min-width: 0; cursor: crosshair; }
</style>
