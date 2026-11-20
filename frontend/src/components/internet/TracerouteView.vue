<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TracerouteHop } from '@/stores/internet'

const props = defineProps<{
  hops: TracerouteHop[]
  target: string
  maxHops: number
  protocol: string
  sessionId: string
}>()

const emit = defineEmits<{
  (e: 'run'): void
}>()

const loading = ref(false)

function runTraceroute() {
  loading.value = true
  emit('run')
}

function getHopStatusClass(hop: TracerouteHop): string {
  if (hop.status === 'success') return 'hop-success'
  if (hop.status === 'timeout') return 'hop-timeout'
  if (hop.status === 'error') return 'hop-error'
  return 'hop-unknown'
}

function getHopStatusLabel(hop: TracerouteHop): string {
  switch (hop.status) {
    case 'success': return 'สำเร็จ'
    case 'timeout': return 'หมดเวลา'
    case 'error': return `ข้อผิดพลาด`
    default: return 'ไม่ทราบ'
  }
}

function formatRtt(rtt: number | null): string {
  if (rtt === null) return '—'
  return `${rtt.toFixed(1)} ms`
}

function formatAddress(hop: TracerouteHop): string {
  if (hop.address) return hop.address
  return hop.status === 'timeout' ? '*' : '?'
}
</script>

<template>
  <div class="traceroute-view" data-testid="traceroute-view">
    <div class="traceroute-header">
      <div class="target-info">
        <h3>Traceroute to {{ target }}</h3>
        <div class="target-meta">
          <span class="meta-item">Protocol: {{ protocol.toUpperCase() }}</span>
          <span class="meta-item">Max Hops: {{ maxHops }}</span>
          <span class="meta-item">Session: {{ sessionId.slice(0, 8) }}</span>
        </div>
      </div>
      <button
        type="button"
        class="btn-run"
        @click="runTraceroute"
        :disabled="loading"
        data-testid="traceroute-run-btn"
      >
        <span v-if="loading" class="spinner-sm" aria-hidden="true"></span>
        {{ loading ? 'Running...' : 'Run Traceroute' }}
      </button>
    </div>

    <div v-if="!hops?.length" class="empty-state" data-testid="traceroute-empty">
      <p>No traceroute data. Click "Run Traceroute" to start.</p>
    </div>

    <div v-else class="hops-table-wrapper">
      <table class="hops-table" data-testid="traceroute-table">
        <thead>
          <tr>
            <th>Hop</th>
            <th>Address</th>
            <th>RTT</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="hop in hops"
            :key="hop.hop"
            :class="getHopStatusClass(hop)"
            :data-testid="`traceroute-hop-${hop.hop}`"
          >
            <td class="hop-num">{{ hop.hop }}</td>
            <td class="hop-address">
              <span class="address">{{ formatAddress(hop) }}</span>
            </td>
            <td class="hop-rtt">{{ formatRtt(hop.rtt_ms) }}</td>
            <td class="hop-status">
              <span class="status-badge" :class="getHopStatusClass(hop)">
                {{ getHopStatusLabel(hop) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="hops?.length" class="traceroute-summary" data-testid="traceroute-summary">
      <div class="summary-stats">
        <span class="stat">
          <span class="stat-value">{{ hops.filter(h => h.status === 'success').length }}</span>
          <span class="stat-label">Successful</span>
        </span>
        <span class="stat">
          <span class="stat-value">{{ hops.filter(h => h.status === 'timeout').length }}</span>
          <span class="stat-label">Timeouts</span>
        </span>
        <span class="stat">
          <span class="stat-value">{{ hops.filter(h => h.status === 'error').length }}</span>
          <span class="stat-label">Errors</span>
        </span>
      </div>
      <div class="summary-destination" v-if="hops[hops.length - 1]?.status === 'success'">
        <span class="dest-icon">🎯</span>
        <span>Destination reached: <strong>{{ hops[hops.length - 1].address }}</strong></span>
      </div>
      <div v-else class="summary-destination incomplete">
        <span class="dest-icon">⚠️</span>
        <span>Destination not reached within {{ maxHops }} hops</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.traceroute-view {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.traceroute-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.target-info h3 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.target-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 12px;
  color: var(--muted);
  font-family: var(--font-mono, ui-monospace, monospace);
}

.btn-run {
  background: var(--accent);
  color: var(--on-accent);
  border: none;
  padding: 8px 16px;
  border-radius: var(--radius-btn);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s ease;
}

.btn-run:hover:not(:disabled) {
  background: var(--accent-strong);
}

.btn-run:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid var(--on-accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.hops-table-wrapper {
  overflow-x: auto;
}

.hops-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.hops-table th,
.hops-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.hops-table th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  font-weight: 600;
  background: var(--panel-2);
  position: sticky;
  top: 0;
}

.hops-table tr:hover td {
  background: var(--panel-2);
}

.hop-num {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 500;
  color: var(--text);
  width: 50px;
}

.hop-address {
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text);
}

.address.timeout {
  color: var(--muted);
}

.hop-rtt {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 500;
  color: var(--text);
  width: 100px;
}

.hop-status { width: 120px; }

.status-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
  display: inline-block;
}

.hop-success .status-badge { background: rgba(34, 211, 238, 0.15); color: #22d3ee; }
.hop-timeout .status-badge { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.hop-error .status-badge { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.hop-unknown .status-badge { background: rgba(100, 116, 139, 0.15); color: #64748b; }

.traceroute-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.summary-stats {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-value {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.stat-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
}

.summary-destination {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(34, 211, 238, 0.1);
  border: 1px solid rgba(34, 211, 238, 0.3);
  border-radius: var(--radius-ctl);
  font-size: 13px;
  color: var(--text);
}

.summary-destination.incomplete {
  background: rgba(251, 191, 36, 0.1);
  border-color: rgba(251, 191, 36, 0.3);
}

.dest-icon { font-size: 16px; }

@media (max-width: 640px) {
  .target-meta { gap: 8px; }
  .summary-stats { gap: 12px; }
}
</style>