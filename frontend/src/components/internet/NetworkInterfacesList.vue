<script setup lang="ts">
import { computed } from 'vue'
import { useInternetStore } from '@/stores/internet'

const store = useInternetStore()

const interfaces = computed(() => store.interfaces?.interfaces ?? [])

function formatRate(bytesPerSec: number): string {
  if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSec / 1024 / 1024).toFixed(2)} MB/s`
}

function getStatusClass(status: string): string {
  return status === 'up' ? 'status-up' : status === 'down' ? 'status-down' : 'status-unknown'
}
</script>

<template>
  <div class="network-interfaces-list" v-if="interfaces.length" data-testid="network-interfaces-list">
    <table class="interfaces-table">
      <thead>
        <tr>
          <th>Interface</th>
          <th>Type</th>
          <th>Status</th>
          <th>Speed</th>
          <th>TX Rate</th>
          <th>RX Rate</th>
          <th>Errors</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="iface in interfaces" :key="iface.id" :data-testid="`interface-row-${iface.id}`">
          <td>
            <div class="iface-name-cell">
              <strong>{{ iface.name }}</strong>
              <span class="iface-connection" v-if="iface.connection_name">{{ iface.connection_name }}</span>
            </div>
          </td>
          <td>{{ iface.type }}</td>
          <td><span class="status-badge" :class="getStatusClass(iface.status)">{{ iface.status }}</span></td>
          <td>{{ iface.speed_mbps ? `${iface.speed_mbps} Mbps` : '—' }}</td>
          <td class="rate-cell">{{ formatRate(iface.current_rates.send_bps) }}</td>
          <td class="rate-cell">{{ formatRate(iface.current_rates.recv_bps) }}</td>
          <td class="errors-cell">
            <span v-if="iface.errors.in || iface.errors.out" class="has-errors">
              In: {{ iface.errors.in }} / Out: {{ iface.errors.out }}
            </span>
            <span v-else class="no-errors">—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <p v-else class="no-interfaces" data-testid="no-interfaces">ไม่พบอินเทอร์เฟซเครือข่าย</p>
</template>

<style scoped>
.network-interfaces-list {
  overflow-x: auto;
}

.interfaces-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.interfaces-table th,
.interfaces-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.interfaces-table th {
  background: var(--panel);
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  font-size: 11px;
  letter-spacing: 0.05em;
}

.iface-name-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.iface-connection {
  font-size: 11px;
  color: var(--muted);
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.status-up {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  color: var(--accent);
}

.status-down {
  background: color-mix(in srgb, var(--bad) 20%, transparent);
  color: var(--bad);
}

.status-unknown {
  background: color-mix(in srgb, var(--muted) 20%, transparent);
  color: var(--muted);
}

.rate-cell {
  font-family: var(--font-mono);
  font-size: 12px;
}

.errors-cell .has-errors {
  color: var(--bad);
  font-weight: 500;
}

.errors-cell .no-errors {
  color: var(--muted);
}

.no-interfaces {
  padding: 24px;
  text-align: center;
  color: var(--muted);
}
</style>