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

const SERIES_DEFS: SeriesDef[] = [
  { key: 'cpu_pct', label: 'CPU %', scale: '%', stroke: '#4fc3f7' },
  { key: 'ram_pct', label: 'RAM %', scale: '%', stroke: '#aed581' },
  { key: 'cpu_temp', label: 'CPU °C', scale: '°C', stroke: '#ff8a65' },
  { key: 'gpu_temp', label: 'GPU °C', scale: '°C', stroke: '#ba68c8' },
  { key: 'disk_temp_max', label: 'Disk °C', scale: '°C', stroke: '#ffb74d' },
  { key: 'cpu_power_w', label: 'CPU W', scale: 'W', stroke: '#fff176' },
  { key: 'gpu_power_w', label: 'GPU W', scale: 'W', stroke: '#ff8a65' },
  { key: 'net_recv_bps', label: 'Net ↓ MB/s', scale: 'MB/s', stroke: '#64b5f6', div: 1048576 },
  { key: 'net_sent_bps', label: 'Net ↑ MB/s', scale: 'MB/s', stroke: '#9575cd', div: 1048576 },
  { key: 'disk_read_bps', label: 'Disk R MB/s', scale: 'MB/s', stroke: '#81c784', div: 1048576 },
  { key: 'disk_write_bps', label: 'Disk W MB/s', scale: 'MB/s', stroke: '#e57373', div: 1048576 },
]

const RANGES: HistoryRange[] = ['1h', '6h', '24h']
const enabled = ref<SeriesKey[]>(['cpu_pct', 'ram_pct', 'cpu_temp', 'gpu_temp', 'cpu_power_w', 'gpu_power_w'])

const chartEl = ref<HTMLElement | null>(null)
let uplot: uPlot | null = null
let resizeObs: ResizeObserver | null = null
let refreshTimer: number | null = null
let renderTimer: number | null = null
let lastSig = ''

// Thermal/power sensors (need admin elevation); covers every °C/W series in SERIES_DEFS.
const THERMAL_KEYS: readonly SeriesKey[] = ['cpu_temp', 'gpu_temp', 'disk_temp_max', 'cpu_power_w', 'gpu_power_w']
const hasThermalData = computed(() =>
  store.points.some(p => THERMAL_KEYS.some(k => p[k] != null)))

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

function render() {
  if (!chartEl.value) return
  const defs = activeDefs()
  const scales = usedScales(defs)
  const css = getComputedStyle(document.documentElement)
  const cBorder = css.getPropertyValue('--border').trim() || '#2d2f55'
  const cMuted = css.getPropertyValue('--muted').trim() || '#a0a0c0'
  const cText = css.getPropertyValue('--text').trim() || '#e6e6ea'

  const axisStyle = {
    stroke: cMuted,
    grid: { stroke: cBorder, width: 0.5 },
    ticks: { stroke: cBorder, width: 0.5 },
    font: '10px ui-monospace, monospace',
  }

  const opts: uPlot.Options = {
    width: chartEl.value.clientWidth || 600,
    height: 280,
    series: [
      {},
      ...defs.map(d => ({
        label: d.label,
        stroke: d.stroke,
        width: 1.6,
        scale: d.scale,
        spanGaps: false,
        value: (_u: uPlot, v: number | null) => fmtVal(d, v),
      })),
    ],
    axes: [{ ...axisStyle }, ...scales.map(s => ({ scale: s, ...axisStyle }))],
    scales: Object.fromEntries(scales.map(s => [s, { auto: true }])),
    legend: { show: true, live: false },
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
  await store.load()
  render()
  resizeObs = new ResizeObserver(() => {
    if (uplot && chartEl.value) {
      uplot.setSize({ width: chartEl.value.clientWidth || 600, height: 280 })
    }
  })
  if (chartEl.value) resizeObs.observe(chartEl.value)
  refreshTimer = window.setInterval(() => {
    if (!document.hidden) store.load()
  }, 60000)
})

watch([enabled, () => store.points], () => scheduleRender())

onBeforeUnmount(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (renderTimer) window.clearTimeout(renderTimer)
  if (resizeObs) resizeObs.disconnect()
  if (uplot) uplot.destroy()
})
</script>

<template>
  <div class="card history-card">
    <div class="head">
      <h3>History</h3>
      <div class="ranges">
        <button
          v-for="r in RANGES"
          :key="r"
          class="range-btn"
          :class="{ active: store.range === r }"
          @click="setRange(r)"
        >{{ r.toUpperCase() }}</button>
      </div>
    </div>

    <div class="chips">
      <button
        v-for="d in SERIES_DEFS"
        :key="d.key"
        class="chip"
        :class="{ on: enabled.includes(d.key) }"
        :style="{ '--chip-color': d.stroke }"
        @click="toggle(d.key)"
      >{{ d.label }}</button>
    </div>

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
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.ranges { display: flex; gap: 6px; }
.range-btn {
  background: transparent; color: var(--muted); border: 1px solid var(--border);
  border-radius: 8px; padding: 4px 10px; font-size: 11px; cursor: pointer;
}
.range-btn.active { color: var(--text); border-color: var(--accent); background: rgba(124,156,255,.12); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 12px; }
.chip {
  background: transparent; border: 1px solid var(--border); color: var(--muted);
  border-radius: 999px; padding: 3px 10px; font-size: 11px; cursor: pointer;
}
.chip.on {
  color: var(--chip-color); border-color: var(--chip-color);
  background: color-mix(in srgb, var(--chip-color) 14%, transparent);
}
.chart { min-width: 0; }
.hint { color: var(--muted); font-size: 12px; margin: 0 0 8px; }
.bad-text { color: var(--bad); }
</style>
