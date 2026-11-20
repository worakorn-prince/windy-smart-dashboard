<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useInternetStore } from '@/stores/internet'
import type { RouteChange } from '@/stores/internet'

const store = useInternetStore()

const props = defineProps<{
  range?: '5m' | '1h' | '6h' | '24h' | '7d' | '30d'
  height?: number
}>()

const range = computed(() => props.range ?? '1h')
const height = computed(() => props.height ?? 200)

const chartEl = ref<HTMLElement | null>(null)
let uplot: uPlot | null = null
let resizeObs: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null

const changes = computed<RouteChange[]>(() => store.routesHistory?.changes ?? [])

const ready = computed(() => changes.value.length > 0)

const changeTypes = computed(() => {
  const types = new Set(changes.value.map(c => c.change_type))
  return Array.from(types).sort()
})

const typeColors: Record<string, string> = {
  added: '#22c55e',
  removed: '#ef4444',
  changed: '#fbbf24',
  updated: '#3b82f6',
}

function buildData(): uPlot.AlignedData {
  const chgs = changes.value
  if (!chgs.length) return [[], []]

  const x: number[] = chgs.map(c => c.timestamp * 1000)
  const y: number[] = chgs.map((_, i) => i)
  return [x, y]
}

function destroyChart() {
  if (uplot) {
    uplot.destroy()
    uplot = null
  }
}

function render() {
  destroyChart()
  if (!chartEl.value || !changes.value.length) return

  const css = getComputedStyle(document.documentElement)
  const cGrid = css.getPropertyValue('--grid-line').trim() || '#16203a'
  const cMuted = css.getPropertyValue('--muted').trim() || '#64748b'

  const seriesDefs = [
    {
      label: 'Changes',
      stroke: '#22d3ee',
      width: 2,
      fill: (u: uPlot): CanvasGradient => {
        const grad = u.ctx.createLinearGradient(0, u.bbox.top, 0, u.bbox.top + u.bbox.height)
        grad.addColorStop(0, 'rgba(34, 211, 238, 0.14)')
        grad.addColorStop(1, 'rgba(34, 211, 238, 0)')
        return grad
      },
      points: { show: true, size: 5, fill: '#22d3ee', stroke: '#00171c', width: 1 },
    },
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
      { scale: 'y', side: 1 },
    ],
    scales: {
      x: { time: true },
      y: { auto: true, min: -0.5, max: changes.value.length - 0.5 },
    },
    legend: { show: false },
    cursor: { points: { show: true, size: 6 } },
    hooks: {
      draw: [
        (u: uPlot) => {
          const { ctx, bbox } = u
          const x0 = u.posToVal(bbox.left, 'x')
          const x1 = u.posToVal(bbox.left + bbox.width, 'x')

          changes.value.forEach((change, i) => {
            const ts = change.timestamp * 1000
            if (ts < x0 || ts > x1) return
            const px = u.valToPos(ts, 'x')
            const py = bbox.top + bbox.height - (i / (changes.value.length - 1 || 1)) * bbox.height

            const color = typeColors[change.change_type] || '#22d3ee'
            ctx.beginPath()
            ctx.arc(px, py, 6, 0, Math.PI * 2)
            ctx.fillStyle = color
            ctx.globalAlpha = 0.3
            ctx.fill()
            ctx.globalAlpha = 1
            ctx.strokeStyle = color
            ctx.lineWidth = 2
            ctx.stroke()
          })
        },
      ],
    },
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

watch(changes, () => scheduleRender(), { flush: 'post' })

onBeforeUnmount(() => {
  if (themeObserver) themeObserver.disconnect()
  if (resizeObs) resizeObs.disconnect()
  destroyChart()
})

function formatTimeAgo(ts: number): string {
  const diff = (Date.now() - ts * 1000) / 1000
  if (diff < 60) return `${Math.floor(diff)} วินาทีที่แล้ว`
  if (diff < 3600) return `${Math.floor(diff / 60)} นาทีที่แล้ว`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ชั่วโมงที่แล้ว`
  return `${Math.floor(diff / 86400)} วันที่แล้ว`
}

function getChangeTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    added: 'เพิ่ม',
    removed: 'ลบ',
    changed: 'เปลี่ยนแปลง',
    updated: 'อัปเดต',
  }
  return labels[type] ?? type
}

function getChangeTypeColor(type: string): string {
  return typeColors[type] || '#22d3ee'
}

function formatDetails(details: Record<string, unknown>): string {
  if (!details || Object.keys(details).length === 0) return '<span class="no-details">—</span>'
  return Object.entries(details)
    .map(([k, v]) => `<span class="detail-pair"><span class="detail-key">${k}:</span> <span class="detail-value">${String(v)}</span></span>`)
    .join(' ')
}
</script>

<template>
  <div class="route-history-chart" data-testid="route-history-chart">
    <div class="chart-header">
      <h3 class="chart-title">Route Changes Over Time</h3>
      <span class="chart-subtitle" v-if="store.routesHistory?.range">
        Range: {{ store.routesHistory.range }}
      </span>
    </div>

    <div v-if="store.loading && !ready" class="loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <span>Loading route history…</span>
    </div>

    <div v-else-if="store.error" class="error-state">
      <p class="error-message">{{ store.error }}</p>
    </div>

    <div v-else-if="!ready" class="empty-state">
      <p>No route changes in this time range</p>
    </div>

    <div v-else ref="chartEl" class="chart" data-testid="route-history-chart-canvas"></div>

    <div v-if="ready" class="legend">
      <span v-for="type in changeTypes" :key="type" class="legend-item">
        <span class="legend-dot" :style="{ background: getChangeTypeColor(type) }"></span>
        {{ getChangeTypeLabel(type) }} ({{ changes.filter(c => c.change_type === type).length }})
      </span>
    </div>

    <div v-if="ready" class="changes-list" data-testid="route-changes-list">
      <div
        v-for="change in changes"
        :key="`${change.timestamp}-${change.change_type}`"
        class="change-item"
        :data-testid="`route-change-${change.timestamp}-${change.change_type}`"
      >
        <span class="change-time">{{ formatTimeAgo(change.timestamp) }}</span>
        <span class="change-type-badge" :style="{ background: getChangeTypeColor(change.change_type) + '20', color: getChangeTypeColor(change.change_type) }">
          {{ getChangeTypeLabel(change.change_type) }}
        </span>
        <span class="change-details" v-html="formatDetails(change.details)"></span>
        <span class="change-severity" :class="`sev-${change.severity.toLowerCase()}`">{{ change.severity }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.route-history-chart {
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
  flex: 1;
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
  padding: 8px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
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

.changes-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
  padding: 8px 0;
}

.change-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-ctl);
  font-size: 12px;
  flex-wrap: wrap;
}

.change-time {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
  min-width: 100px;
}

.change-type-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.change-details {
  flex: 1;
  min-width: 150px;
  color: var(--text-dim);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 11px;
}

.detail-pair { margin-right: 12px; }
.detail-key { color: var(--muted); font-weight: 500; }
.detail-value { color: var(--text); }
.no-details { color: var(--muted); font-style: italic; }

.change-severity {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.change-severity.sev-critical { background: rgba(239, 68, 68, 0.15); color: var(--crit); }
.change-severity.sev-high { background: rgba(248, 113, 113, 0.15); color: var(--bad); }
.change-severity.sev-medium { background: rgba(251, 191, 36, 0.15); color: var(--warn); }
.change-severity.sev-low { background: rgba(74, 222, 128, 0.15); color: var(--good); }

@media (max-width: 640px) {
  .change-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }
  .change-time { min-width: auto; }
  .change-details { min-width: auto; }
}
</style>