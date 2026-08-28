<script setup lang="ts">
import type { AdapterInfo } from '@/stores/metrics'

defineProps<{ adapters: AdapterInfo[] | undefined }>()

function statusBadge(s: string) {
  if (s === 'Connected') return 'badge sev-low'
  if (s.includes('Connecting') || s === 'Authenticating') return 'badge sev-medium'
  if (s.includes('Disabled') || s === 'Media Disconnected' || s.includes('Not Present')) return 'badge high'
  return 'badge'
}
</script>

<template>
  <div class="card">
    <h3>Network Adapters <span class="count" v-if="adapters?.length">({{ adapters.length }})</span></h3>
    <div v-if="adapters && adapters.length" class="table-wrap">
      <table>
        <colgroup>
          <col class="c-name" />
          <col class="c-mac" />
          <col class="c-speed" />
          <col class="c-status" />
          <col class="c-ipv4" />
          <col class="c-gw" />
          <col class="c-dns" />
        </colgroup>
        <thead>
          <tr>
            <th>Adapter</th>
            <th>MAC Address</th>
            <th>Link Speed</th>
            <th>Status</th>
            <th>IPv4</th>
            <th>Gateway</th>
            <th>DNS Servers</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in adapters" :key="a.name">
            <td>
              <div class="adapter-name" :title="a.description">{{ a.name }}</div>
              <div class="muted small" :title="a.description">{{ a.description }}</div>
            </td>
            <td class="mono">{{ a.mac || '—' }}</td>
            <td class="num">{{ a.speed_mbps ? a.speed_mbps + ' Mbps' : '—' }}</td>
            <td><span :class="statusBadge(a.status)">{{ a.status }}</span></td>
            <td>
              <div v-for="ip in a.ipv4" :key="ip" class="mono ip-line">{{ ip }}</div>
              <span v-if="!a.ipv4.length" class="muted small">—</span>
              <div v-for="ip6 in a.ipv6" :key="ip6" class="mono ip-line muted small">{{ ip6 }}</div>
            </td>
            <td>
              <div v-for="gw in a.gateway" :key="gw" class="mono ip-line">{{ gw }}</div>
              <span v-if="!a.gateway.length" class="muted small">—</span>
            </td>
            <td>
              <div v-for="dns in a.dns" :key="dns" class="mono ip-line">{{ dns }}</div>
              <span v-if="!a.dns.length" class="muted small">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted">Waiting for data…</p>
  </div>
</template>

<style scoped>
.count { color: var(--muted); font-weight: 500; text-transform: none; letter-spacing: 0; }

.table-wrap { overflow-x: auto; }

table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 12px;
}

th, td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}
th {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
}
tbody tr:hover { background: rgba(124, 156, 255, 0.05); }

/* Generous column widths — readable at full card width */
.c-name   { width: 22%; }
.c-mac    { width: 14%; }
.c-speed  { width: 9%; }
.c-status { width: 11%; }
.c-ipv4   { width: 16%; }
.c-gw     { width: 12%; }
.c-dns    { width: auto; }

.adapter-name {
  font-weight: 600;
  font-size: 12.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  word-break: break-all;
}
.ip-line { line-height: 1.5; }
.num { font-variant-numeric: tabular-nums; }

.badge.sev-low { background: var(--good); color: #082a14; }
.badge.sev-medium { background: var(--warn); color: #2a1f08; }
.badge.high { background: var(--bad); color: #fff; }
</style>