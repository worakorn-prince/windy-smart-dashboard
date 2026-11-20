<script setup lang="ts">
import { computed } from 'vue'
import { useInternetStore } from '@/stores/internet'
import StatTile from '@/components/dashboard/StatTile.vue'

const store = useInternetStore()

const props = defineProps<{
  targetId?: 'primary' | 'secondary' | 'gateway'
}>()

const targetId = computed(() => props.targetId ?? 'primary')

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
  gap: 16px;
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