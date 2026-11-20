<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useInternetStore } from '@/stores/internet'
import type { DnsHistoryPoint, DnsBucketedPoint } from '@/stores/internet'

const store = useInternetStore()

const props = defineProps<{
  range?: '5m' | '1h' | '6h' | '24h' | '7d' | '30d'
  height?: number
  resolver?: string
}>()

const range = computed(() => props.range ?? '1h')
const height = computed(() => props.height ?? 200)
const resolver = computed(() => props.resolver ?? '')

const chartEl = ref<HTMLElement | null>(null)
let uplot: uPlot | null = null
let resizeObs: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null

const points = computed<((DnsHistoryPoint | DnsBucketedPoint) & { resolver?: string })[]>(() => {
  const pts = store.dnsHistory?.points ?? []
  if (!resolver.value) return pts
  return pts.filter(p => (p as any).resolver === resolver.value)
})

const isBucketed = computed(() => {
  const pts = points.value
  return pts.length > 0 && 'latency' in pts[0]!
})

const ready = computed(() => points.value.length > 0)

function buildData(): uPlot.AlignedData {
  const pts = points.value
  if (!pts.length) return [[], [], [], [], []]

  const x: number[] = pts.map(p => p.ts * 1000)

  if (isBucketed.value) {
    const median: (number | null)[] = pts.map(p => (p as DnsBucketedPoint).latency.median)
    const min: (number | null)[] = pts.map(p => (p as DnsBucketedPoint).latency.min)
    const max: (number | null)[] = pts.map(p => (p as DnsBucketedPoint).latency.max)
    const p95: (number | null)[] = pts.map(p => (p as DnsBucketedPoint).latency.p95)
    return [x, median, min, max, p95]
  } else {
    const duration: (number | null)[] = pts.map(p => (p as DnsHistoryPoint).duration_ms)
    return [x, duration]
  }
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

function destroyChart() {
  if (uplot) {
    uplot.destroy()
    uplot = null
  }
}

function render() {
  destroyChart()
  if (!chartEl.value || !points.value.length) return

  const css = getComputedStyle(document.documentElement)
  const cGrid = css.getPropertyValue('--grid-line').trim() || '#16203a'
  const cMuted = css.getPropertyValue('--muted').trim() || '#64748b'

  const axisStyle = {
    stroke: cMuted,
    grid: { stroke: cGrid, width: 1 },
    ticks: { stroke: cGrid, width: 1 },
    font: '11px ui-monospace, monospace',
  }

  const seriesDefs = isBucketed.value
    ? [
        { label: 'Median', stroke: '#22d3ee', width: 2, fill: makeFill('#22d3ee'), scale: 'ms', spanGaps: true, value: (_u: uPlot, v: number | null) => v != null ? `${v.toFixed(1)} ms` : '-' },
        { label: 'Min', stroke: '#22d3ee', width: 0.5, strokeDash: [4, 4], scale: 'ms', spanGaps: true, value: () => '' },
        { label: 'Max', stroke: '#f87171', width: 0.5, strokeDash: [4, 4], scale: 'ms', spanGaps: true, value: () => '' },
        { label: 'P95', stroke: '#a78bfa', width: 1.5, strokeDash: [6, 4], scale: 'ms', spanGaps: true, value: (_u: uPlot, v: number | null) => v != null ? `${v.toFixed(1)} ms` : '-' },
      ]
    : [
        { label: 'Duration', stroke: '#22d3ee', width: 2, fill: makeFill('#22d3ee'), scale: 'ms', spanGaps: false, value: (_u: uPlot, v: number | null) => v != null ? `${v.toFixed(1)} ms` : '-' },
      ]

  const opts: uPlot.Options = {
    width: chartEl.value.clientWidth || 600,
    height: height.value,
    series: [
      {},
      ...seriesDefs,
    ],
    axes: [
      { scale: 'x' },
      { scale: 'ms' },
    ],
    scales: {
      x: { time: true },
      ms: { auto: true },
    },
    legend: { show: false },
    cursor: { points: { show: false } },
  }

  uplot = new uPlot(opts, buildData(), chartEl.value)
}

function scheduleRender() {
  if (!chartEl.value) return
  render()
}

onMounted(() => {
  themeObserver = new MutationObserver(() => scheduleRender())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  resizeObs = new ResizeObserver(() => {
    if (uplot && chartEl.value) {
      uplot.setSize({ width: chartEl.value.clientWidth || 600, height: height.value })
    }
  })
  if (chartEl.value) resizeObs.observe(chartEl.value)
  scheduleRender()
})

watch([points, () => store.dnsHistory?.step], () => scheduleRender(), { flush: 'post' })

onBeforeUnmount(() => {
  if (themeObserver) themeObserver.disconnect()
  if (resizeObs) resizeObs.disconnect()
  destroyChart()
})
</script>

<template>
  <div class="dns-history-chart" :data-testid="`dns-history-chart-${resolver || 'all'}`">
    <div class="chart-header">
      <h3 class="chart-title">
        {{ resolver ? `${resolver} DNS Latency` : 'DNS Latency (All Resolvers)' }}
      </h3>
      <span class="chart-subtitle" v-if="store.dnsHistory?.step">
        Bucket: {{ store.dnsHistory.step }}s
      </span>
    </div>

    <div v-if="store.loading && !ready" class="loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <span>Loading DNS history…</span>
    </div>

    <div v-else-if="store.error" class="error-state">
      <p class="error-message">{{ store.error }}</p>
    </div>

    <div v-else-if="!ready" class="empty-state">
      <p>No DNS history data{{ resolver ? ` for ${resolver}` : '' }}</p>
    </div>

    <div v-else ref="chartEl" class="chart" data-testid="dns-history-chart-canvas"></div>

    <div v-if="ready" class="legend">
      <span v-if="isBucketed" class="legend-item">
        <span class="legend-dot" style="background: #22d3ee"></span> Median
      </span>
      <span v-if="isBucketed" class="legend-item">
        <span class="legend-dot" style="background: #22d3ee; border-style: dashed"></span> Min/Max
      </span>
      <span v-if="isBucketed" class="legend-item">
        <span class="legend-dot" style="background: #a78bfa; border-style: dashed"></span> P95
      </span>
      <span v-else class="legend-item">
        <span class="legend-dot" style="background: #22d3ee"></span> Duration
      </span>
    </div>
  </div>
</template>

<style scoped>
.dns-history-chart {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chart-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.chart-subtitle {
  font-size: 11px;
  color: var(--muted);
  font-family: var(--font-mono);
  background: var(--panel-2);
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
}

.chart {
  min-width: 0;
  cursor: crosshair;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  gap: 12px;
  color: var(--muted);
  font-size: 13px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-message {
  margin: 0;
  color: var(--bad);
  font-size: 13px;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  font-size: 11px;
  color: var(--text-dim);
  font-family: var(--font-mono, ui-monospace, monospace);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  border: 1px solid transparent;
}

.legend-dot[style*="dashed"] {
  border-style: dashed;
  border-radius: 2px;
}
</style>