<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useInternetStore } from '@/stores/internet'
import StatTile from '@/components/dashboard/StatTile.vue'
import type { HistoryPoint, BucketedLatencyPoint } from '@/stores/internet'

const store = useInternetStore()

const props = defineProps<{
  targetId?: 'primary' | 'secondary' | 'gateway'
  showSparkline?: boolean
}>()

const targetId = computed(() => props.targetId ?? 'primary')
const showSparkline = computed(() => props.showSparkline ?? true)

const target = computed(() => {
  if (!store.quality?.targets) return null
  return store.quality.targets.find(t => t.target_id === targetId.value) ?? null
})

const latency = computed(() => target.value?.latency_ms)

const hasData = computed(() => target.value !== null)

const address = computed(() => target.value?.address ?? '—')
const probeType = computed(() => target.value?.probe_type ?? '—')
const status = computed(() => target.value?.status ?? 'unavailable')

const medianLatency = computed(() => latency.value?.median)
const minLatency = computed(() => latency.value?.min)
const maxLatency = computed(() => latency.value?.max)
const p95Latency = computed(() => latency.value?.p95)
const jitter = computed(() => target.value?.jitter_ms)
const lossPct = computed(() => target.value?.loss_pct ?? 0)
const count = computed(() => latency.value?.count ?? 0)
const timeouts = computed(() => latency.value?.timeouts ?? 0)
const lastProbe = computed(() => target.value?.last_probe_at ?? 0)

const statusClass = computed(() => {
  switch (status.value) {
    case 'success': return 'text-good'
    case 'degraded': return 'text-warn'
    case 'timeout': return 'text-bad'
    default: return 'text-muted'
  }
})

const lossClass = computed(() => {
  const loss = lossPct.value
  if (loss > 5) return 'amber'
  if (loss > 1) return 'amber'
  if (loss > 0) return 'amber'
  return 'cyan'
})

// Sparkline
const sparklineEl = ref<HTMLElement | null>(null)
let sparklineUplot: uPlot | null = null
let sparklineResizeObs: ResizeObserver | null = null
let sparklineThemeObserver: MutationObserver | null = null

const historyPoints = computed<((HistoryPoint | BucketedLatencyPoint) & { target_id?: string })[]>(() =>
  store.qualityHistory?.points?.filter(p => (p as any).target_id === targetId.value) ?? []
)

const sparklineReady = computed(() => historyPoints.value.length > 0)

function buildSparklineData(): uPlot.AlignedData {
  const pts = historyPoints.value
  if (!pts.length) return [[], []]

  const x: number[] = pts.map(p => p.ts * 1000)
  let y: (number | null)[]

  if (pts.length > 0 && 'latency' in pts[0]!) {
    // Bucketed data - use median
    y = pts.map(p => (p as BucketedLatencyPoint).latency.median)
  } else {
    // Raw data - use rtt_ms
    y = pts.map(p => (p as HistoryPoint).rtt_ms)
  }

  return [x, y]
}

function renderSparkline() {
  if (!sparklineEl.value || !sparklineReady.value) return

  const css = getComputedStyle(document.documentElement)
  const cGrid = css.getPropertyValue('--grid-line').trim() || '#16203a'
  const cMuted = css.getPropertyValue('--muted').trim() || '#64748b'

  const statusColor = statusClass.value === 'text-good' ? '#4ade80'
    : statusClass.value === 'text-warn' ? '#fbbf24'
    : statusClass.value === 'text-bad' ? '#f87171'
    : '#64748b'

  const axisStyle = {
    stroke: 'transparent',
    grid: { stroke: 'transparent', width: 0 },
    ticks: { stroke: 'transparent', width: 0 },
    font: '10px ui-monospace, monospace',
  }

  const opts: uPlot.Options = {
    width: sparklineEl.value.clientWidth || 180,
    height: 40,
    series: [
      {},
      {
        label: 'Latency',
        stroke: statusColor,
        width: 1.5,
        fill: (u: uPlot): CanvasGradient => {
          const grad = u.ctx.createLinearGradient(0, u.bbox.top, 0, u.bbox.top + u.bbox.height)
          grad.addColorStop(0, hexToRgba(statusColor, 0.18))
          grad.addColorStop(1, hexToRgba(statusColor, 0))
          return grad
        },
        scale: 'ms',
        spanGaps: true,
        value: () => '',
      },
    ],
    axes: [
      { scale: 'x', ...axisStyle, show: false },
      { scale: 'ms', ...axisStyle, show: false },
    ],
    scales: {
      x: { time: true },
      ms: { auto: true },
    },
    legend: { show: false },
    cursor: { show: false },
  }

  if (sparklineUplot) {
    sparklineUplot.destroy()
    sparklineUplot = null
  }
  sparklineUplot = new uPlot(opts, buildSparklineData(), sparklineEl.value)
}

function hexToRgba(hex: string, alpha: number): string {
  const raw = hex.replace('#', '')
  const full = raw.length === 3 ? raw.split('').map(c => c + c).join('') : raw.padEnd(6, '0').slice(0, 6)
  const r = parseInt(full.slice(0, 2), 16) || 0
  const g = parseInt(full.slice(2, 4), 16) || 0
  const b = parseInt(full.slice(4, 6), 16) || 0
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function scheduleSparklineRender() {
  if (!sparklineEl.value) return
  renderSparkline()
}

onMounted(() => {
  if (!showSparkline.value) return
  sparklineThemeObserver = new MutationObserver(() => scheduleSparklineRender())
  sparklineThemeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  sparklineResizeObs = new ResizeObserver(() => {
    if (sparklineUplot && sparklineEl.value) {
      sparklineUplot.setSize({ width: sparklineEl.value.clientWidth || 180, height: 40 })
    }
  })
  if (sparklineEl.value) sparklineResizeObs.observe(sparklineEl.value)
  scheduleSparklineRender()
})

watch([historyPoints, () => store.qualityHistory?.step], () => scheduleSparklineRender(), { flush: 'post' })

onBeforeUnmount(() => {
  if (sparklineThemeObserver) sparklineThemeObserver.disconnect()
  if (sparklineResizeObs) sparklineResizeObs.disconnect()
  if (sparklineUplot) sparklineUplot.destroy()
})

function formatTimeAgo(ts: number): string {
  if (!ts) return '—'
  const diff = (Date.now() - ts * 1000) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
</script>

<template>
  <div class="quality-summary" :data-testid="`quality-summary-${targetId}`">
    <header class="quality-header">
      <div class="target-info">
        <h3 class="target-name" :data-testid="`quality-target-name-${targetId}`">
          {{ targetId === 'primary' ? 'Primary Target' : targetId === 'secondary' ? 'Secondary Target' : 'Gateway' }}
        </h3>
        <div class="target-meta">
          <span class="meta-item">{{ address }} ({{ probeType }})</span>
          <span class="meta-item status-badge" :class="statusClass">{{ status }}</span>
        </div>
      </div>
      <span v-if="lastProbe" class="last-probe" :data-testid="`quality-last-probe-${targetId}`">
        Probe: {{ formatTimeAgo(lastProbe) }}
      </span>
    </header>

    <div v-if="hasData && showSparkline && sparklineReady" class="sparkline-container" ref="sparklineEl" data-testid="quality-sparkline"></div>

    <div v-if="hasData" class="quality-metrics" data-testid="quality-metrics-grid">
      <StatTile
        label="Latency (median)"
        :value="(medianLatency as number | null) !== null ? (medianLatency as number).toFixed(1) : '—'"
        unit="ms"
        accent="cyan"
        icon="⏱️"
        data-testid="stat-latency-median"
      />

      <StatTile
        label="Jitter"
        :value="(jitter as number | null) !== null ? (jitter as number).toFixed(1) : '—'"
        unit="ms"
        :accent="(jitter as number | null) !== null && (jitter as number) > 30 ? 'amber' : (jitter as number | null) !== null && (jitter as number) > 10 ? 'amber' : 'cyan'"
        icon="📊"
        data-testid="stat-jitter"
      />

      <StatTile
        label="Packet Loss"
        :value="lossPct.toFixed(1)"
        unit="%"
        :accent="lossClass"
        icon="📉"
        data-testid="stat-packet-loss"
      />

      <StatTile
        label="Min Latency"
        :value="(minLatency as number | null) !== null ? (minLatency as number).toFixed(1) : '—'"
        unit="ms"
        accent="lime"
        icon="▼"
        data-testid="stat-latency-min"
      />

      <StatTile
        label="Max Latency"
        :value="(maxLatency as number | null) !== null ? (maxLatency as number).toFixed(1) : '—'"
        unit="ms"
        accent="amber"
        icon="▲"
        data-testid="stat-latency-max"
      />

      <StatTile
        label="P95 Latency"
        :value="(p95Latency as number | null) !== null ? (p95Latency as number).toFixed(1) : '—'"
        unit="ms"
        :accent="(p95Latency as number | null) !== null ? 'violet' : 'cyan'"
        icon="📈"
        data-testid="stat-latency-p95"
      />

      <StatTile
        label="Samples"
        :value="String(count)"
        accent="cyan"
        icon="🔢"
        data-testid="stat-samples"
      />

      <StatTile
        label="Timeouts"
        :value="String(timeouts)"
        :accent="timeouts > 0 ? 'amber' : 'cyan'"
        icon="⏱️"
        data-testid="stat-timeouts"
      />
    </div>

    <div v-else class="quality-empty" data-testid="quality-empty">
      <p>No quality data available for {{ targetId }}</p>
    </div>
  </div>
</template>

<style scoped>
.quality-summary {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quality-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.target-name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.target-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.meta-item {
  font-size: 11px;
  color: var(--muted);
  font-family: var(--font-mono);
}

.status-badge {
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-badge.text-good { background: rgba(74, 222, 128, 0.15); color: var(--good); }
.status-badge.text-warn { background: rgba(251, 191, 36, 0.15); color: var(--warn); }
.status-badge.text-bad { background: rgba(248, 113, 113, 0.15); color: var(--bad); }
.status-badge.text-muted { background: rgba(100, 116, 139, 0.15); color: var(--muted); }

.last-probe {
  font-size: 11px;
  color: var(--muted);
  font-family: var(--font-mono);
  white-space: nowrap;
}

.sparkline-container {
  height: 40px;
  min-width: 0;
}

.quality-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.quality-empty {
  padding: 24px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 640px) {
  .quality-metrics {
    grid-template-columns: 1fr 1fr;
  }
}
</style>