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

const rawPoints = computed(() => {
  const points = store.qualityHistory?.points ?? []
  return points.filter(p => 'rtt_ms' in p && (p as any).target_id === targetId.value) as Array<{
    ts: number;
    target_id: string;
    probe_type: string;
    rtt_ms: number | null;
    status: string;
    error_code: string | null;
    timeout_ms: number | null;
  }>
})

const ready = computed(() => rawPoints.value.length > 0)

// Error code colors for stacked bars
const ERROR_COLORS: Record<string, string> = {
  TIMEOUT: '#f87171',
  UNREACHABLE: '#fb923c',
  NETWORK_UNREACHABLE: '#f97316',
  CONNECTION_REFUSED: '#f472b6',
  DNS_FAILURE: '#a78bfa',
  ERROR: '#94a3b8',
  default: '#64748b',
}

const ERROR_LABELS: Record<string, string> = {
  TIMEOUT: 'Timeout',
  UNREACHABLE: 'Unreachable',
  NETWORK_UNREACHABLE: 'Network Unreachable',
  CONNECTION_REFUSED: 'Connection Refused',
  DNS_FAILURE: 'DNS Failure',
  ERROR: 'Error',
  default: 'Other',
}

const activeErrorCodes = computed(() => {
  const codes = new Set<string>()
  for (const p of rawPoints.value) {
    if (p.status !== 'success' && p.error_code) {
      codes.add(p.error_code)
    }
  }
  return Array.from(codes)
})

function buildData(): uPlot.AlignedData {
  const pts = rawPoints.value
  if (!pts.length) return [[], []]

  // Bucket by time intervals
  const step = store.qualityHistory?.step ?? 60
  const buckets: Map<number, HistoryPoint[]> = new Map()

  for (const p of pts) {
    const bucketTs = Math.floor(p.ts / step) * step
    if (!buckets.has(bucketTs)) buckets.set(bucketTs, [])
    buckets.get(bucketTs)!.push(p)
  }

  const sortedBuckets = Array.from(buckets.entries()).sort((a, b) => a[0] - b[0])

  const x: number[] = sortedBuckets.map(([ts]) => ts * 1000)
  const seriesMap: Map<string, (number | null)[]> = new Map()

  // Initialize all error types
  for (const code of Object.keys(ERROR_COLORS)) {
    seriesMap.set(code, new Array(x.length).fill(null))
  }

  // Fill series data
  sortedBuckets.forEach(([, bucketPts], i) => {
    const total = bucketPts.length
    if (total === 0) return

    const errorCounts: Record<string, number> = {}
    for (const p of bucketPts) {
      if (p.status !== 'success' && p.error_code) {
        errorCounts[p.error_code] = (errorCounts[p.error_code] || 0) + 1
      }
    }

    for (const [code, count] of Object.entries(errorCounts)) {
      const series = seriesMap.get(code)
      if (series) series[i] = (count / bucketPts.length) * 100
    }
  })

  // Convert map to array of series in uPlot AlignedData tuple format: [x, series1, series2, ...]
  const seriesArrays: (number | null)[][] = [x]
  for (const code of Object.keys(ERROR_COLORS)) {
    seriesArrays.push(seriesMap.get(code) ?? new Array(x.length).fill(null))
  }

  return seriesArrays as uPlot.AlignedData
}

function render() {
  if (!chartEl.value) return
  destroyChart()

  const data = buildData()
  if (!data[0].length) return

  const step = store.qualityHistory?.step ?? 60
  const x = data[0]
  const errorCodes = Object.keys(ERROR_COLORS)

  // Build series array using for loop to avoid TS spread issues
  const seriesArray: uPlot.Series[] = [{}]
  for (const code of errorCodes) {
    const seriesItem: uPlot.Series = {
      stroke: ERROR_COLORS[code],
      fill: (self: uPlot, seriesIdx: number): CanvasRenderingContext2D['fillStyle'] => {
        const grad = self.ctx.createLinearGradient(0, self.bbox.top, 0, self.bbox.top + self.bbox.height)
        grad.addColorStop(0, hexToRgba(ERROR_COLORS[code], 0.25))
        grad.addColorStop(1, 'transparent')
        return grad
      },
      width: 1,
      spanGaps: true,
    }
    seriesArray.push(seriesItem)
  }

  const opts: uPlot.Options = {
    width: chartEl.value?.clientWidth ?? 600,
    height: height.value,
    title: '',
    scales: {
      x: { time: true },
      y: { auto: true, min: 0, max: 100 },
    },
    axes: [
      { scale: 'x', incrs: [60] },
      { scale: 'y' },
    ],
    series: seriesArray,
    legend: { show: false },
    cursor: { show: true, points: { show: false } },
    hooks: {
      draw: [
        (u: uPlot) => {
          // Stack series manually - access data via u.data
          if (u.data.length < 2) return
          for (let i = 1; i < u.data.length; i++) {
            const prev = u.data[i - 1]
            const curr = u.data[i]
            if (!curr || !prev) continue
            for (let j = 0; j < curr.length; j++) {
              const currVal = curr[j]
              const prevVal = prev[j]
              if (currVal != null && prevVal != null) {
                curr[j] = currVal + prevVal
              }
            }
          }
        },
      ],
    },
  }

  uplot = new uPlot(opts, data, chartEl.value)
}

function destroyChart() {
  if (uplot) {
    uplot.destroy()
    uplot = null
  }
}

function scheduleRender() {
  if (!chartEl.value) return
  render()
}

function hexToRgba(hex: string, alpha: number): string {
  const raw = hex.replace('#', '')
  const full = raw.length === 3 ? raw.split('').map(c => c + c).join('') : raw.padEnd(6, '0').slice(0, 6)
  const r = parseInt(full.slice(0, 2), 16) || 0
  const g = parseInt(full.slice(2, 4), 16) || 0
  const b = parseInt(full.slice(4, 6), 16) || 0
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
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
  <div class="packet-loss-chart" :data-testid="`packet-loss-chart-${targetId}`">
    <div class="chart-header">
      <h3 class="chart-title">{{ targetId === 'primary' ? 'Primary' : targetId === 'secondary' ? 'Secondary' : 'Gateway' }} Packet Loss</h3>
      <span class="chart-subtitle">Stacked by error type</span>
    </div>

    <div v-if="store.loading && !ready" class="loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <span>Loading packet loss history…</span>
    </div>

    <div v-else-if="store.error" class="error-state">
      <p class="error-message">{{ store.error }}</p>
    </div>

    <div v-else-if="!ready" class="empty-state">
      <p>No packet loss data for {{ targetId }}</p>
    </div>

    <div v-else ref="chartEl" class="chart" data-testid="packet-loss-chart-canvas"></div>

    <div v-if="ready" class="legend">
      <span v-for="code in activeErrorCodes" :key="code" class="legend-item">
        <span class="legend-dot" :style="{ background: ERROR_COLORS[code] ?? ERROR_COLORS.default }"></span>
        {{ ERROR_LABELS[code] ?? code }}
      </span>
      <span v-if="!activeErrorCodes.length" class="legend-item">
        <span class="legend-dot" style="background: #22d3ee"></span> No loss
      </span>
    </div>
  </div>
</template>

<style scoped>
.packet-loss-chart {
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
  border: 1px solid var(--border).
}

.chart {
  width: 100%;
  min-height: 200px;
}

.loading-state,
.empty-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  gap: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  gap: 12px;
  color: var(--muted);
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
  gap: 12px;
  font-size: 11px;
  color: var(--text);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>