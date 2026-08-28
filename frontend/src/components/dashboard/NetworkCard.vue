<script setup lang="ts">
import type { NetworkSnapshot } from '@/stores/metrics'
import { formatBytes, formatRate } from '@/composables/format'

defineProps<{ network: NetworkSnapshot | null; ping: { latency_ms: number; target: string } }>()
</script>

<template>
  <div class="card">
    <h3>Network</h3>
    <div v-if="network">
      <!-- Upload/Download -->
      <div class="section">
        <h4>Throughput</h4>
        <div class="info-grid">
          <div class="info-row">
            <span class="label">↑ Upload</span>
            <span class="value">{{ formatRate(network.send_bytes_per_sec) }}</span>
          </div>
          <div class="info-row">
            <span class="label">↓ Download</span>
            <span class="value">{{ formatRate(network.recv_bytes_per_sec) }}</span>
          </div>
          <div class="info-row">
            <span class="label">Total Sent</span>
            <span class="value">{{ formatBytes(network.bytes_sent) }}</span>
          </div>
          <div class="info-row">
            <span class="label">Total Received</span>
            <span class="value">{{ formatBytes(network.bytes_recv) }}</span>
          </div>
        </div>
      </div>

      <!-- Ping -->
      <div class="section">
        <h4>Latency</h4>
        <div class="row">
          <span class="label">Ping to {{ ping.target }}</span>
          <span class="value" :class="pingColor(ping.latency_ms)">{{ ping.latency_ms.toFixed(1) }} ms</span>
        </div>
      </div>

      <!-- Public IP -->
      <div class="section" v-if="network.public_ip">
        <h4>Public IP</h4>
        <div class="row wrap-row">
          <span class="label">External IP</span>
          <span class="value kbd">{{ network.public_ip }}</span>
        </div>
      </div>

      <!-- WiFi -->
      <div class="section" v-if="network.wifi">
        <h4>WiFi</h4>
        <div class="info-grid">
          <div class="info-row">
            <span class="label">SSID</span>
            <span class="value"><strong>{{ network.wifi.SSID }}</strong></span>
          </div>
          <div class="info-row">
            <span class="label">Signal</span>
            <span class="value" :class="signalColor(network.wifi.Signal)">{{ network.wifi.Signal }}%</span>
          </div>
          <div class="info-row">
            <span class="label">BSSID</span>
            <span class="kbd" :title="network.wifi.BSSID">{{ network.wifi.BSSID }}</span>
          </div>
          <div class="info-row">
            <span class="label">Channel</span>
            <span class="value">{{ network.wifi.Channel }}</span>
          </div>
          <div class="info-row">
            <span class="label">Radio</span>
            <span class="value">{{ network.wifi.RadioType }}</span>
          </div>
        </div>
      </div>
    </div>
    <p v-else class="muted">Waiting for data…</p>
  </div>
</template>

<script lang="ts">
function signalColor(s: number) {
  if (s >= 80) return 'text-sev-low'
  if (s >= 60) return 'text-sev-medium'
  if (s >= 40) return 'text-sev-high'
  return 'text-sev-critical'
}

function pingColor(ms: number) {
  if (ms < 20) return 'text-sev-low'
  if (ms < 50) return 'text-sev-medium'
  if (ms < 100) return 'text-sev-high'
  return 'text-sev-critical'
}
</script>

<style scoped>
.section { margin-bottom: 16px; }
.section h4 { margin: 0 0 8px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }

/* wrap-row: allow long values (IPs, MACs) to drop to the next line */
.row.wrap-row {
  flex-wrap: wrap;
  gap: 4px 12px;
}
.row.wrap-row .value { white-space: normal; }

/* min-width: 0 is critical — without it, grid children refuse to shrink
   below their content width and long text overflows the card frame. */
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
  margin-top: 8px;
}
.info-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.info-row .label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.3px; }
.info-row .value {
  font-size: 12px;
  font-weight: 500;
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-all;
  white-space: normal;
  line-height: 1.4;
}

table { width: 100%; border-collapse: collapse; font-size: 11px; table-layout: fixed; }
th, td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
th { color: var(--muted); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
td { font-size: 11px; }

.kbd {
  font-family: 'JetBrains Mono', monospace;
  background: var(--panel-2);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  display: inline-block;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-all;
  white-space: normal;
}

.text-sev-low { color: var(--good); }
.text-sev-medium { color: var(--warn); }
.text-sev-high { color: var(--bad); }
.text-sev-critical { color: var(--crit); font-weight: 700; }
</style>