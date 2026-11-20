<script setup lang="ts">
import { computed } from 'vue'
import type { DnsResolverHealth } from '@/stores/internet'

const props = defineProps<{
  resolver: DnsResolverHealth
}>()

const statusLabel = computed(() => {
  switch (props.resolver.status) {
    case 'ok': return 'ปกติ'
    case 'degraded': return 'ลดประสิทธิภาพ'
    case 'down': return 'ล้มเหลว'
    default: return 'ไม่ทราบ'
  }
})

const statusColor = computed(() => {
  switch (props.resolver.status) {
    case 'ok': return 'cyan'
    case 'degraded': return 'amber'
    case 'down': return 'red'
    default: return 'muted'
  }
})

const latencyDisplay = computed(() => {
  const val = props.resolver.avg_latency_ms
  return val !== null ? `${val.toFixed(1)} ms` : '—'
})

const successRateDisplay = computed(() => {
  return `${(props.resolver.success_rate * 100).toFixed(1)}%`
})

function formatTimeAgo(ts: number | null): string {
  if (!ts) return '—'
  const diff = (Date.now() - ts * 1000) / 1000
  if (diff < 60) return `${Math.floor(diff)} วินาทีที่แล้ว`
  if (diff < 3600) return `${Math.floor(diff / 60)} นาทีที่แล้ว`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ชั่วโมงที่แล้ว`
  return `${Math.floor(diff / 86400)} วันที่แล้ว`
}
</script>

<template>
  <div class="resolver-card" :data-testid="`resolver-card-${resolver.resolver}`">
    <div class="card-header">
      <div class="resolver-info">
        <span class="resolver-address" :data-testid="`resolver-address-${resolver.resolver}`">{{ resolver.resolver }}</span>
        <span class="status-badge" :class="`status-${resolver.status}`" :data-testid="`resolver-status-${resolver.resolver}`">
          {{ statusLabel }}
        </span>
      </div>
    </div>

    <div class="metrics-grid" data-testid="resolver-metrics">
      <div class="metric">
        <span class="metric-label">Latency (เฉลี่ย)</span>
        <span class="metric-value" :data-testid="`resolver-latency-${resolver.resolver}`">{{ latencyDisplay }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">อัตราสำเร็จ</span>
        <span class="metric-value" :data-testid="`resolver-success-${resolver.resolver}`">{{ successRateDisplay }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">โปรบล่าสุด</span>
        <span class="metric-value" :data-testid="`resolver-probes-${resolver.resolver}`">{{ resolver.recent_probes }}</span>
      </div>
      <div class="metric">
        <span class="metric-label">ตรวจสอบล่าสุด</span>
        <span class="metric-value" :data-testid="`resolver-last-${resolver.resolver}`">{{ formatTimeAgo(resolver.last_probe_at) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.resolver-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.resolver-address {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.status-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.status-ok { background: rgba(34, 211, 238, 0.15); color: #22d3ee; }
.status-degraded { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.status-down { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.status-unknown { background: rgba(100, 116, 139, 0.15); color: #64748b; }

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.metric-value {
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text);
}

@media (max-width: 640px) {
  .metrics-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>