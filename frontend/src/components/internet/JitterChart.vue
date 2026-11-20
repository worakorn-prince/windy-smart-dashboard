<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useInternetStore } from '@/stores/internet'
import type { HistoryPoint } from '@/stores/internet'

const store = useInternetStore()

const props = defineProps<{
  targetId?: 'primary' | 'secondary' | 'gateway'
  range?: '5m' | '1h' | '6h' | '24h' | '7d' | '30d'
  height?: number
}>()

const targetId = computed(() => props.targetId ?? 'primary')
const range = computed(() => props.range ?? '1h')
const height = computed(() => props.height ?? 200)

const chartEl = ref<HTMLElement | null>(null)
let uplot: uPlot | null = null
let resizeObs: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null

const rawPoints = computed(() =>
  (store.qualityHistory?.points?.filter(p => 'rtt_ms' in p && (p as any).target_id === targetId.value) ?? []) as HistoryPoint[]
)

const ready = computed(() => rawPoints.value.length > 1)

function buildData(): uPlot.AlignedData {
  const pts = rawPoints.value
  if (pts.length < 2) return [[], []]

  // Compute jitter as mean absolute difference between consecutive successful RTTs
  const successful = pts.filter(p => p.rtt_ms != null && p.status === 'success')
  if (successful.length < 2) return [[], []]

  const x: number[] = []
  const jitter: (number | null)[] = []

  for (let i = 1; i < successful.length; i++) {
    const diff = Math.abs(successful[i].rtt_ms! - successful[i - 1].rtt_ms!)
    x.push(successful[i].ts * 1000)
    jitter.push(diff)
  }

  return [x, jitter]
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
  if (!chartEl.value || !ready.value) return

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
    height: height.value,
    series: [
      {},
      {
        label: 'Jitter (|ΔRTT|)',
        stroke: '#fbbf24',
        width: 2,
        fill: makeFill('#fbbf24'),
        scale: 'ms',
        spanGaps: false,
        value: (_u: uPlot, v: number | null) => v != null ? `${v.toFixed(1)} ms` : '-',
      },
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

watch([rawPoints, () => store.qualityHistory?.step], () => scheduleRender(), { flush: 'post' })

onBeforeUnmount(() => {
  if (themeObserver) themeObserver.disconnect()
  if (resizeObs) resizeObs.disconnect()
  destroyChart()
})
</script>

<template>
  <div class="jitter-chart" :data-testid="`jitter-chart-${targetId}`">
    <div class="chart-header">
      <h3 class="chart-title">{{ targetId === 'primary' ? 'Primary' : targetId === 'secondary' ? 'Secondary' : 'Gateway' }} Jitter</h3>
      <span class="chart-subtitle">Mean |ΔRTT|</span>
    </div>

    <div v-if="store.loading && !ready" class="loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <span>Loading jitter history…</span>
    </div>

    <div v-else-if="store.error" class="error-state">
      <p class="error-message">{{ store.error }}</p>
    </div>

    <div v-else-if="!ready" class="empty-state">
      <p>Insufficient data for jitter calculation</p>
    </div>

    <div v-else ref="chartEl" class="chart" data-testid="jitter-chart-canvas"></div>

    <div v-if="ready" class="legend">
      <span class="legend-item">
        <span class="legend-dot" style="background: #fbbf24"></span> Jitter (ms)
      </span>
    </div>
  </div>
</template>

<style scoped>
.jitter-chart {
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
}
</style>