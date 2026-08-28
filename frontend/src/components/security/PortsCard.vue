<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSecurityStore } from '@/stores/security'

const store = useSecurityStore()
const showKillConfirm = ref<number | null>(null)
const killResult = ref<string>('')
const killBusy = ref(false)

interface PortRow {
  pid: number
  name: string
  exe: string
  port: number
  ip: string
  signed: boolean
}

const listening = computed<PortRow[]>(() => store.audit?.data?.net?.listening ?? [])

async function doKill(pid: number) {
  killBusy.value = true
  try {
    const res = await store.killProcess(pid)
    killResult.value = res.ok
      ? `Killed PID ${pid} (${res.name})`
      : `Failed: ${res.reason || 'unknown'}`
    showKillConfirm.value = null
  } finally {
    killBusy.value = false
    setTimeout(() => (killResult.value = ''), 5000)
  }
}
</script>

<template>
  <div class="card ports-card">
    <h3>Listening Ports <span class="count" v-if="listening.length">({{ listening.length }})</span></h3>
    <p class="muted small result-line" v-if="killResult">{{ killResult }}</p>

    <div v-if="listening.length" class="table-wrap">
      <table>
        <colgroup>
          <col class="c-port" />
          <col class="c-ip" />
          <col class="c-pid" />
          <col class="c-name" />
          <col class="c-sig" />
          <col class="c-act" />
        </colgroup>
        <thead>
          <tr>
            <th>Port</th>
            <th>IP</th>
            <th>PID</th>
            <th>Process</th>
            <th>Signature</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in listening" :key="p.pid + ':' + p.port">
            <td class="num">{{ p.port }}</td>
            <td class="mono">{{ p.ip }}</td>
            <td class="num">{{ p.pid }}</td>
            <td class="name-cell" :title="p.exe">{{ p.name }}</td>
            <td>
              <span class="sig-badge" :class="p.signed ? 'ok' : 'warn'">{{ p.signed ? 'signed' : 'unverified' }}</span>
            </td>
            <td class="act-cell">
              <template v-if="showKillConfirm === p.pid">
                <button class="btn tiny warn-btn" :disabled="killBusy" @click="doKill(p.pid)">
                  {{ killBusy ? '…' : 'Confirm' }}
                </button>
                <button class="btn tiny" @click="showKillConfirm = null">Cancel</button>
              </template>
              <button v-else class="btn tiny danger-btn" @click="showKillConfirm = p.pid">Kill</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted">Run audit to populate.</p>
  </div>
</template>

<style scoped>
.ports-card { width: 100%; }
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
  word-break: break-word;
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
.c-port { width: 9%; }
.c-ip   { width: 18%; }
.c-pid  { width: 9%; }
.c-name { width: auto; }
.c-sig  { width: 13%; }
.c-act  { width: 17%; }

.num { font-variant-numeric: tabular-nums; }
.mono, .name-cell {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name-cell { cursor: default; }

.sig-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
}
.sig-badge.ok { background: rgba(95, 217, 124, 0.15); color: var(--good); }
.sig-badge.warn { background: rgba(255, 215, 95, 0.15); color: var(--warn); }

.act-cell { white-space: nowrap; display: flex; gap: 6px; align-items: center; }

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
.warn-btn { background: var(--warn); border-color: var(--warn); color: #1a1a1a; }
</style>