<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSecurityStore } from '@/stores/security'

const store = useSecurityStore()
const blockIpInput = ref('')
const actionResult = ref('')
const blockBusy = ref('')

interface ConnRow {
  pid: number
  name: string
  local: string
  remote_ip: string
  remote_port: number
  geo: {
    available: boolean
    country?: string
    country_code?: string
    city?: string
    isp?: string
    suspicious_country?: boolean
    is_tor?: boolean
    reason?: string
    private?: boolean
  }
}

const established = computed<ConnRow[]>(() => store.audit?.data?.net?.established ?? [])

async function block(ip: string) {
  if (!ip || blockBusy.value) return
  blockBusy.value = ip
  try {
    const res = await store.blockIp(ip)
    actionResult.value = res.ok ? `Blocked ${ip}` : `Failed: ${res.reason || 'unknown'}`
    if (res.ok) blockIpInput.value = ''
    setTimeout(() => (actionResult.value = ''), 5000)
  } finally {
    blockBusy.value = ''
  }
}
</script>

<template>
  <div class="card conn-card">
    <h3>Outbound Connections <span class="count" v-if="established.length">({{ established.length }})</span></h3>
    <p class="muted small result-line" v-if="actionResult">{{ actionResult }}</p>

    <div v-if="established.length" class="table-wrap">
      <table>
        <colgroup>
          <col class="c-target" />
          <col class="c-country" />
          <col class="c-isp" />
          <col class="c-proc" />
          <col class="c-act" />
        </colgroup>
        <thead>
          <tr>
            <th>Target</th>
            <th>Country</th>
            <th>ISP / Org</th>
            <th>Process</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(c, i) in established" :key="i">
            <td class="mono target-cell">
              {{ c.remote_ip }}:{{ c.remote_port }}
              <span v-if="c.geo?.is_tor" class="tor-badge">TOR</span>
            </td>
            <td>
              <span v-if="c.geo?.available" class="country" :class="{ suspicious: c.geo.suspicious_country }">
                <strong>{{ c.geo.country_code }}</strong> {{ c.geo.country }}
                <span v-if="c.geo.suspicious_country" class="flag">⚠️</span>
              </span>
              <span v-else class="muted small">{{ c.geo?.reason ? `(${c.geo.reason})` : '—' }}</span>
            </td>
            <td class="isp-cell" :title="c.geo?.isp">{{ c.geo?.isp || '—' }}</td>
            <td class="proc-cell" v-auto-tip><span class="num">{{ c.pid }}</span> {{ c.name }}</td>
            <td class="act-cell">
              <button class="btn tiny danger-btn"
                      :disabled="blockBusy === c.remote_ip"
                      @click="block(c.remote_ip)">
                {{ blockBusy === c.remote_ip ? '…' : 'Block IP' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted">Run audit to populate.</p>
  </div>
</template>

<style scoped>
.conn-card { width: 100%; }
.count { color: var(--muted); font-weight: 500; text-transform: none; letter-spacing: 0; }
.result-line { margin: 0 0 8px; }

.table-wrap { overflow-x: auto; }

table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 12px;
}

th, td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  overflow-wrap: break-word;
}
th {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
}
tbody tr:hover { background: rgba(124, 156, 255, 0.05); }

/* Column proportions */
.c-target  { width: 24%; }
.c-country { width: 18%; }
.c-isp     { width: auto; }
.c-proc    { width: 20%; }
.c-act     { width: 11%; }

.mono, .target-cell {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
}
.target-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }

.tor-badge {
  background: rgba(255, 69, 69, 0.2);
  color: var(--crit);
  font-size: 9px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: 'Segoe UI', sans-serif;
}

.country strong { font-size: 12px; }
.country.suspicious { color: var(--bad); }
.flag { margin-left: 4px; }

.isp-cell, .proc-cell {
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.num { font-variant-numeric: tabular-nums; }

.act-cell { white-space: nowrap; }

.btn {
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}
.btn.tiny { padding: 3px 10px; font-size: 11px; line-height: 1.4; }
.btn.tiny:hover:not(:disabled) { background: var(--border); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.danger-btn:hover:not(:disabled) { background: var(--bad); border-color: var(--bad); color: #fff; }
</style>