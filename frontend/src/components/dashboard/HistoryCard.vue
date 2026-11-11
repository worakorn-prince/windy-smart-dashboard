<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useHistoryStore, type HistoryPoint, type HistoryRange } from '@/stores/history'

const store = useHistoryStore()

type SeriesKey = Exclude<keyof HistoryPoint, 'ts'>

interface SeriesDef {
  key: SeriesKey
  label: string
  scale: string
  stroke: string
  div?: number
}

const BYTES_PER_MB = 1024 * 1024

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

const RANGES: HistoryRange[] = ['5m', '1h', '6h', '24h']
const RANGE_LABELS: Record<HistoryRange, string> = {
  '5m': '5 นาที',
  '1h': '1 ชม.',
  '6h': '6 ชม.',
  '24h': '24 ชม.',
}
const STORAGE_KEY = 'history.enabled'
const TAB_STORAGE_KEY = 'history.tab'

type HistoryTab = 'cpu' | 'ram' | 'gpu' | 'network' | 'disk'

interface TabDef {
  id: HistoryTab
  label: string
  keys: SeriesKey[]
}

const TABS: TabDef[] = [
  { id: 'cpu', label: 'CPU', keys: ['cpu_pct', 'cpu_temp', 'cpu_power_w'] },
  { id: 'ram', label: 'RAM', keys: ['ram_pct', 'swap_pct'] },
  { id: 'gpu', label: 'GPU', keys: ['gpu_temp', 'gpu_power_w'] },
  { id: 'network', label: 'Network', keys: ['net_recv_bps', 'net_sent_bps'] },
  { id: 'disk', label: 'Disk', keys: ['disk_read_bps', 'disk_write_bps', 'disk_temp_max'] },
]

function tabKeys(id: HistoryTab): SeriesKey[] {
  return TABS.find(t => t.id === id)?.keys ?? TABS[0]!.keys
}

const activeTab = ref<HistoryTab>('cpu')
const enabled = ref<SeriesKey[]>([...tabKeys('cpu')])

const chartEl = ref<HTMLElement | null>(null)
let uplot: uPlot | null = null
let resizeObs: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null
let refreshTimer: number | null = null
let renderTimer: number | null = null
let lastSig = ''

// Thermal/power sensors (need admin elevation); covers every °C/W series in SERIES_DEFS.
const THERMAL_KEYS: readonly SeriesKey[] = ['cpu_temp', 'gpu_temp', 'disk_temp_max', 'cpu_power_w', 'gpu_power_w']
const hasThermalData = computed(() =>
  store.points.some(p => THERMAL_KEYS.some(k => p[k] != null)))
const refreshing = computed(() => store.loading && store.points.length > 0)

function loadTab(): void {
  try {
    const raw = localStorage.getItem(TAB_STORAGE_KEY)
    if (TABS.some(t => t.id === raw)) activeTab.value = raw as HistoryTab
  } catch { /* keep default tab on storage errors */ }
}

function loadEnabled(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      enabled.value = [...tabKeys(activeTab.value)]
      return
    }
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) {
      enabled.value = [...tabKeys(activeTab.value)]
      return
    }
    const valid = parsed.filter((k): k is SeriesKey =>
      SERIES_DEFS.some(d => d.key === k))
    enabled.value = valid.length ? valid : [...tabKeys(activeTab.value)]
  } catch {
    enabled.value = [...tabKeys(activeTab.value)]
  }
}

function selectTab(id: HistoryTab) {
  if (id === activeTab.value) return
  activeTab.value = id
  enabled.value = [...tabKeys(id)]
  try { localStorage.setItem(TAB_STORAGE_KEY, id) } catch { /* storage unavailable */ }
}

function refreshChart(): void {
  render()
}

const tabDefs = computed(() => SERIES_DEFS.filter(d => tabKeys(activeTab.value).includes(d.key)))

function toggle(key: SeriesKey) {
  const i = enabled.value.indexOf(key)
  // Reassign (not mutate) so the watch() source reference changes and
  // the chart re-renders immediately.
  enabled.value = i >= 0
    ? enabled.value.filter(k => k !== key)
    : [...enabled.value, key]
}

function setRange(r: HistoryRange) {
  if (r !== store.range) store.load(r)
}

function activeDefs(): SeriesDef[] {
  return SERIES_DEFS.filter(d => enabled.value.includes(d.key))
}

function usedScales(defs: SeriesDef[]): string[] {
  const out: string[] = []
  for (const d of defs) if (!out.includes(d.scale)) out.push(d.scale)
  return out
}

function fmtVal(d: SeriesDef, v: number | null): string {
  if (v == null) return '-'
  if (d.div) return v.toFixed(2)
  if (d.scale === '%' || d.scale === '°C') return v.toFixed(1)
  if (d.scale === 'W') return v.toFixed(1)
  return v.toFixed(0)
}

function buildData(): uPlot.AlignedData {
  const pts = store.points
  const x: number[] = pts.map(p => p.ts)
  const ys: (number | null)[][] = activeDefs().map(d => pts.map(p => {
    const v: number | null = p[d.key]
    return v == null ? null : (d.div ? v / d.div : v)
  }))
  return [x, ...ys]
}

function hexToRgba(hex: string, alpha: number): string {
  const raw = hex.replace('#', '')
  const full = raw.length === 3
    ? raw.split('').map(c => c + c).join('')
    : raw.padEnd(6, '0').slice(0, 6)
  const r = parseInt(full.slice(0, 2), 16) || 0
  const g = parseInt(full.slice(2, 4), 16) || 0
  const b = parseInt(full.slice(4, 6), 16) || 0
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function makeFill(color: string) {
  return (u: uPlot): CanvasGradient => {
    const grad = u.ctx.createLinearGradient(0, u.bbox.top, 0, u.bbox.top + u.bbox.height)
    grad.addColorStop(0, hexToRgba(color, 0.18))
    grad.addColorStop(1, hexToRgba(color, 0))
    return grad
  }
}

const legendDefs = computed(() => SERIES_DEFS.filter(d => enabled.value.includes(d.key)))

function render() {
  if (!chartEl.value) return
  const defs = activeDefs()
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

  const opts: uPlot.Options = {
    width: chartEl.value.clientWidth || 600,
    height: 340,
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
    ],
    axes: [{ ...axisStyle }, ...scales.map(s => ({ scale: s, ...axisStyle }))],
    scales: Object.fromEntries(scales.map(s => [s, { auto: true }])),
    legend: { show: false },
    cursor: { points: { show: false } },
  }

  if (uplot) {
    uplot.destroy()
    uplot = null
  }
  uplot = new uPlot(opts, buildData(), chartEl.value)
  lastSig = chartSig(defs)
}

function chartSig(defs: SeriesDef[]): string {
  const pts = store.points
  const last = pts.length ? pts[pts.length - 1]!.ts : 0
  return `${store.range}|${defs.map(d => d.key).join(',')}|${pts.length}|${last}`
}

function scheduleRender() {
  if (renderTimer) window.clearTimeout(renderTimer)
  renderTimer = window.setTimeout(() => {
    renderTimer = null
    if (!chartEl.value) return
    if (chartSig(activeDefs()) === lastSig) return
    render()
  }, 120)
}

onMounted(async () => {
  loadEnabled()
  await loadTab()
  await store.load()
  render()
  themeObserver = new MutationObserver(() => refreshChart())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  resizeObs = new ResizeObserver(() => {
    if (uplot && chartEl.value) {
      uplot.setSize({ width: chartEl.value.clientWidth || 600, height: 340 })
    }
  })
  if (chartEl.value) resizeObs.observe(chartEl.value)
  refreshTimer = window.setInterval(() => {
    if (!document.hidden) store.load()
  }, 60000)
})

watch([enabled, () => store.points], () => scheduleRender())

watch(enabled, (v) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(v)) } catch { /* storage unavailable */ }
})

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (renderTimer) window.clearTimeout(renderTimer)
  if (themeObserver) themeObserver.disconnect()
  if (resizeObs) resizeObs.disconnect()
  if (uplot) uplot.destroy()
})
</script>

<template>
  <div class="card history-card">
    <div class="head">
      <div class="head-text">
        <h3 class="card-title">
          กราฟประวัติการใช้งาน
          <span v-if="refreshing" class="updating">กำลังอัปเดต…</span>
        </h3>
        <p class="subtitle">แบบเรียลไทม์: CPU, GPU และ RAM</p>
      </div>
      <div class="ranges">
        <button
          v-for="r in RANGES"
          :key="r"
          class="range-btn"
          :class="{ active: store.range === r }"
          @click="setRange(r)"
        >{{ RANGE_LABELS[r] }}</button>
      </div>
    </div>

    <div data-testid="history-tabs" class="tabs">
      <button data-testid="history-tab-cpu" class="tab-btn" :class="{ active: activeTab === 'cpu' }" @click="selectTab('cpu')">CPU</button>
      <button data-testid="history-tab-ram" class="tab-btn" :class="{ active: activeTab === 'ram' }" @click="selectTab('ram')">RAM</button>
      <button data-testid="history-tab-gpu" class="tab-btn" :class="{ active: activeTab === 'gpu' }" @click="selectTab('gpu')">GPU</button>
      <button data-testid="history-tab-network" class="tab-btn" :class="{ active: activeTab === 'network' }" @click="selectTab('network')">เครือข่าย</button>
      <button data-testid="history-tab-disk" class="tab-btn" :class="{ active: activeTab === 'disk' }" @click="selectTab('disk')">ดิสก์</button>
    </div>

    <div class="chips">
      <button
        v-for="d in tabDefs"
        :key="d.key"
        class="chip"
        :class="{ on: enabled.includes(d.key) }"
        :style="{ '--chip-color': d.stroke }"
        @click="toggle(d.key)"
      >{{ d.label }}</button>
    </div>

    <div class="legend">
      <span v-for="d in legendDefs" :key="d.key" class="legend-item">
        <span class="legend-dot" :style="{ background: d.stroke, color: d.stroke }"></span>
        {{ d.label }}
      </span>
    </div>

    <p v-if="store.loading && !store.points.length" class="hint">Loading history…</p>
    <p v-if="store.error" class="hint bad-text">Failed to load history: {{ store.error }}</p>
    <p v-else-if="!store.loading && !store.points.length" class="hint">
      No samples yet — collecting every 10s.
    </p>
    <p v-else-if="!hasThermalData" class="hint">
      Temperatures need admin elevation — run via elevated PowerShell.
    </p>

    <div ref="chartEl" class="chart"></div>
  </div>
</template>

<style scoped>
.history-card { min-width: 0; }
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.head-text { min-width: 0; }
.card-title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 0.02em;
  text-transform: none;
  white-space: normal;
}
.subtitle { margin: 4px 0 0; font-size: 12px; color: var(--muted); }
.ranges {
  display: flex;
  gap: 6px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px;
}
.range-btn {
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  font-family: var(--font-mono, ui-monospace, monospace);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.range-btn:hover { color: var(--text); border-color: var(--border-strong); }
.range-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 700;
}
.tabs { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 2px; }
.tab-btn {
  background: transparent; color: var(--text-dim); border: 1px solid var(--border);
  border-radius: 999px; padding: 3px 12px; font-size: 12px; cursor: pointer;
}
.tab-btn:hover { color: var(--text); border-color: var(--border-strong); }
.tab-btn.active {
  color: var(--accent);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  font-weight: 600;
}
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 10px; }
.chip {
  background: transparent; border: 1px solid var(--border); color: var(--muted);
  border-radius: 999px; padding: 3px 10px; font-size: 12px; cursor: pointer;
}
.chip.on {
  color: var(--chip-color); border-color: var(--chip-color);
  background: color-mix(in srgb, var(--chip-color) 14%, transparent);
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
.chart { min-width: 0; cursor: crosshair; }
.hint { color: var(--muted); font-size: 12px; margin: 0 0 8px; }
.updating { margin-left: 8px; color: var(--muted); font-size: 12px; font-weight: 400; }
.bad-text { color: var(--bad); }
</style>
