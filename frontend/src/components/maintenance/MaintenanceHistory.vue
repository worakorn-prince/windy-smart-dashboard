<script setup lang="ts">
import { useMaintenanceStore, type HistoryEntry } from '@/stores/maintenance'

const store = useMaintenanceStore()

function text(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) return value.map(text).join(', ')
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function formatDate(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const raw = String(value)
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

function historyTime(h: HistoryEntry): string {
  return formatDate(h.at ?? h.timestamp ?? h.time ?? h.createdAt ?? h.ts)
}

function historyAction(h: HistoryEntry): string {
  return text(h.action ?? h.operation ?? h.type)
}

function historyTarget(h: HistoryEntry): string {
  return text(h.target ?? h.targets ?? h.scope)
}

function historyStatus(h: HistoryEntry): string {
  return text(h.status ?? h.result ?? (h.ok === true ? 'ok' : h.ok === false ? 'failed' : ''))
}

function historyMessage(h: HistoryEntry): string {
  return text(h.message ?? h.detail ?? h.reason ?? h.summary ?? h.error)
}

function statusClass(h: HistoryEntry): string {
  const status = historyStatus(h).toLowerCase()
  if (status === 'ok' || status === 'success' || status === 'done') return 'ok'
  if (status === '—') return ''
  return 'warn'
}

function loadHistory() {
  return store.loadHistory()
}
</script>

<template>
  <div class="card maintenance-history">
    <h3>
      ประวัติการบำรุงรักษา ({{ store.history.length }})
      <button class="btn tiny" :disabled="store.busy === 'history'" @click="loadHistory">
        {{ store.busy === 'history' ? 'กำลังโหลด…' : 'โหลดประวัติ' }}
      </button>
    </h3>

    <div v-if="store.history.length" class="table-wrap">
      <table>
        <colgroup>
          <col class="c-time" />
          <col class="c-action" />
          <col class="c-target" />
          <col class="c-status" />
          <col class="c-message" />
        </colgroup>
        <thead>
          <tr>
            <th>เวลา</th>
            <th>การทำงาน</th>
            <th>เป้าหมาย</th>
            <th>สถานะ</th>
            <th>ข้อความ</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(h, i) in store.history" :key="i">
            <td class="mono">{{ historyTime(h) }}</td>
            <td>{{ historyAction(h) }}</td>
            <td class="mono">
              <span class="text-truncate" v-auto-tip>{{ historyTarget(h) }}</span>
            </td>
            <td>
              <span class="sig-badge" :class="statusClass(h)">{{ historyStatus(h) }}</span>
            </td>
            <td class="message-cell">
              <span class="text-truncate" v-auto-tip>{{ historyMessage(h) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted">ยังไม่มีประวัติ — กดปุ่ม "โหลดประวัติ" เพื่อดึงข้อมูล</p>
  </div>
</template>

<style scoped>
h3 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.btn {
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}
.btn.tiny { padding: 3px 10px; font-size: 11px; line-height: 1.4; }
.btn:hover:not(:disabled) { background: var(--border); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.table-wrap { overflow-x: auto; overflow-y: auto; max-height: 460px; }

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

.c-time { width: 18%; }
.c-action { width: 18%; }
.c-target { width: 16%; }
.c-status { width: 12%; }
.c-message { width: 36%; }

.mono, .message-cell {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
}
.text-truncate { display: block; min-width: 0; }

.sig-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
}
.sig-badge.ok { background: rgba(95, 217, 124, 0.15); color: var(--good); }
.sig-badge.warn { background: rgba(255, 215, 95, 0.15); color: var(--warn); }
</style>
