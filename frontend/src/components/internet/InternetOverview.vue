<script setup lang="ts">
import { computed } from 'vue'
import { useInternetStore } from '@/stores/internet'
import StatTile from '@/components/dashboard/StatTile.vue'
import { formatRate } from '@/composables/format'

const store = useInternetStore()

const connectionStatus = computed(() => {
  if (!store.overview) return 'unknown'
  return store.overview.connection_status
})

const connectionStatusLabel = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return 'เชื่อมต่อแล้ว'
    case 'degraded': return 'คุณภาพลดลง'
    case 'disconnected': return 'ตัดการเชื่อมต่อ'
    default: return 'ไม่ทราบสถานะ'
  }
})

const connectionStatusColor = computed(() => {
  switch (connectionStatus.value) {
    case 'connected': return 'cyan'
    case 'degraded': return 'amber'
    case 'disconnected': return 'amber'
    default: return 'cyan'
  }
})

const activeInterfaceName = computed(() => {
  if (!store.overview?.active_interface) return '—'
  return store.overview.active_interface.name ?? store.overview.active_interface.id ?? '—'
})

const activeInterfaceSpeed = computed(() => {
  if (!store.overview?.active_interface) return '—'
  const speed = store.overview.active_interface.speed_mbps
  return speed ? `${speed} Mbps` : '—'
})

const throughputSend = computed(() => {
  if (!store.overview?.current_throughput) return '0 B/s'
  return formatRate(store.overview.current_throughput.send_bps)
})

const throughputRecv = computed(() => {
  if (!store.overview?.current_throughput) return '0 B/s'
  return formatRate(store.overview.current_throughput.recv_bps)
})

const primaryLatency = computed(() => {
  const val = store.primaryLatency
  return val !== null ? `${val.toFixed(1)} ms` : '—'
})

const primaryLoss = computed(() => {
  const val = store.primaryLoss
  return `${val.toFixed(1)}%`
})

const gatewayLatency = computed(() => {
  const val = store.gatewayLatency
  return val !== null ? `${val.toFixed(1)} ms` : '—'
})

const incidentsCount = computed(() => {
  return store.overview?.recent_incidents.length ?? 0
})
</script>

<template>
  <div class="internet-overview">
    <section class="overview-grid" data-testid="internet-overview-grid">
      <StatTile
        label="สถานะการเชื่อมต่อ"
        :value="connectionStatusLabel"
        :accent="connectionStatusColor"
        :icon="connectionStatus === 'connected' ? '●' : connectionStatus === 'degraded' ? '◑' : '○'"
        data-testid="stat-connection-status"
      />

      <StatTile
        label="อินเทอร์เฟซที่ใช้งาน"
        :value="activeInterfaceName"
        :subtitle="activeInterfaceSpeed"
        accent="cyan"
        icon="📡"
        data-testid="stat-active-interface"
      />

      <StatTile
        label="อัพโหลด"
        :value="throughputSend"
        accent="lime"
        icon="↑"
        data-testid="stat-upload"
      />

      <StatTile
        label="ดาวน์โหลด"
        :value="throughputRecv"
        accent="violet"
        icon="↓"
        data-testid="stat-download"
      />

      <StatTile
        label="เลตันซี Primary"
        :value="primaryLatency"
        accent="cyan"
        icon="🎯"
        data-testid="stat-primary-latency"
      />

      <StatTile
        label="Packet Loss Primary"
        :value="primaryLoss"
        :accent="store.primaryLoss > 1 ? 'amber' : store.primaryLoss > 0 ? 'amber' : 'cyan'"
        icon="📉"
        data-testid="stat-primary-loss"
      />

      <StatTile
        label="เลตันซี Gateway"
        :value="gatewayLatency"
        accent="amber"
        icon="🚪"
        data-testid="stat-gateway-latency"
      />

      <StatTile
        label="Incidents ใกล้เคียง"
        :value="String(incidentsCount)"
        :accent="incidentsCount > 0 ? 'amber' : 'cyan'"
        icon="⚠️"
        data-testid="stat-incidents"
      />
    </section>

    <section v-if="store.overview?.dns_health" class="dns-section" data-testid="dns-health-section">
      <h3>DNS Health</h3>
      <div class="dns-grid">
        <div class="dns-item">
          <span class="dns-label">Configured</span>
          <span class="dns-value">{{ store.overview.dns_health.configured.join(', ') || '—' }}</span>
        </div>
        <div class="dns-item">
          <span class="dns-label">Primary</span>
          <span class="dns-value" :class="dnsStatusClass(store.overview.dns_health.primary_status)">{{ store.overview.dns_health.primary_status }}</span>
        </div>
        <div class="dns-item">
          <span class="dns-label">Secondary</span>
          <span class="dns-value" :class="dnsStatusClass(store.overview.dns_health.secondary_status)">{{ store.overview.dns_health.secondary_status }}</span>
        </div>
      </div>
    </section>

    <section v-if="store.overview?.recent_incidents?.length" class="incidents-section" data-testid="recent-incidents-section">
      <h3>Incidents ใกล้เคียง</h3>
      <ul class="incidents-list">
        <li v-for="inc in store.overview.recent_incidents" :key="inc.id" class="incident-item">
          <span class="incident-severity" :class="`sev-${inc.severity.toLowerCase()}`">{{ inc.severity }}</span>
          <span class="incident-title">{{ inc.title }}</span>
          <span class="incident-time">{{ formatTimeAgo(inc.started_at) }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<script lang="ts">
function dnsStatusClass(status: string): string {
  return status === 'ok' ? 'text-good' : 'text-bad'
}

function formatTimeAgo(ts: number): string {
  const diff = (Date.now() - ts * 1000) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
</script>

<style scoped>
.internet-overview {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.dns-section,
.incidents-section {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
}

.dns-section h3,
.incidents-section h3 {
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.dns-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.dns-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dns-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted);
}

.dns-value {
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-mono);
}

.dns-value.text-good { color: var(--good); }
.dns-value.text-bad { color: var(--bad); }

.incidents-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.incident-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--panel-2);
  border-radius: var(--radius-ctl);
  border: 1px solid var(--border);
}

.incident-severity {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.incident-severity.sev-critical { background: rgba(239, 68, 68, 0.15); color: var(--crit); }
.incident-severity.sev-high { background: rgba(248, 113, 113, 0.15); color: var(--bad); }
.incident-severity.sev-medium { background: rgba(251, 191, 36, 0.15); color: var(--warn); }
.incident-severity.sev-low { background: rgba(74, 222, 128, 0.15); color: var(--good); }

.incident-title {
  flex: 1;
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.incident-time {
  font-size: 11px;
  color: var(--muted);
  font-family: var(--font-mono);
  white-space: nowrap;
}

@media (max-width: 640px) {
  .overview-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>