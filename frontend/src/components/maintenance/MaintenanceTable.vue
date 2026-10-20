<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DriverDevice, ScanCounts } from '@/stores/maintenance'

const props = defineProps<{
  devices: DriverDevice[]
  counts: ScanCounts
  scanning?: boolean
}>()

type SortKey = 'name' | 'status' | 'problem' | 'version' | 'date'
type SortDir = 'asc' | 'desc'

const SORT_STORAGE_KEY = 'dashboard:maintenance:sort'
const SORT_KEYS: SortKey[] = ['name', 'status', 'problem', 'version', 'date']

const columns: { key: SortKey; label: string; colClass: string }[] = [
  { key: 'name', label: 'อุปกรณ์', colClass: 'c-name' },
  { key: 'status', label: 'สถานะ', colClass: 'c-status' },
  { key: 'problem', label: 'ปัญหา', colClass: 'c-problem' },
  { key: 'version', label: 'เวอร์ชัน', colClass: 'c-version' },
  { key: 'date', label: 'วันที่', colClass: 'c-date' },
]

function readStoredSort(): { key: SortKey; dir: SortDir } {
  try {
    const raw = localStorage.getItem(SORT_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as { key?: string; dir?: string }
      const key = parsed.key as SortKey
      if (SORT_KEYS.includes(key)) {
        return { key, dir: parsed.dir === 'desc' ? 'desc' : 'asc' }
      }
    }
  } catch {
    // localStorage unavailable or malformed value — fall back to defaults.
  }
  return { key: 'name', dir: 'asc' }
}

const stored = readStoredSort()
const sortKey = ref<SortKey>(stored.key)
const sortDir = ref<SortDir>(stored.dir)

watch([sortKey, sortDir], ([key, dir]) => {
  try {
    localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify({ key, dir }))
  } catch {
    // Persisting the sort preference is best-effort only.
  }
})

function ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
  if (sortKey.value !== key) return 'none'
  return sortDir.value === 'asc' ? 'ascending' : 'descending'
}

function toggleSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

function text(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function devName(d: DriverDevice): string {
  return text(d.name ?? d.deviceName ?? d.friendlyName ?? d.instanceId)
}

function devStatus(d: DriverDevice): string {
  return text(d.status ?? d.Status)
}

function devVersion(d: DriverDevice): string {
  return text(d.version ?? d.driverVersion ?? d.driver_version)
}

function devDateValue(d: DriverDevice): unknown {
  return d.date ?? d.driverDate ?? d.driver_date
}

function devDate(d: DriverDevice): string {
  const raw = devDateValue(d)
  if (raw === null || raw === undefined || raw === '') return '—'
  const parsed = new Date(String(raw))
  if (Number.isNaN(parsed.getTime())) return String(raw)
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'short' })
}

function devError(d: DriverDevice): string {
  const value = d.errorText ?? d.error
  return value === null || value === undefined || value === '' ? '' : String(value)
}

function devProblem(d: DriverDevice): string {
  const value = d.problem ?? d.problemCode ?? d.problem_code
  if (value === null || value === undefined || value === '') return '—'
  return String(value)
}

function problemLabel(d: DriverDevice): string {
  return devError(d) || devProblem(d)
}

function problemNumber(d: DriverDevice): number | null {
  const value = d.problem ?? d.problemCode ?? d.problem_code
  if (value === null || value === undefined || value === '') return null
  const raw = String(value)
  const upper = raw.toUpperCase()
  if (raw === '0' || upper === 'CM_PROB_NONE' || raw === 'null' || raw === 'undefined') return null
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

function isIssue(d: DriverDevice): boolean {
  if (devError(d)) return true
  const status = String(d.status ?? d.Status ?? '').toUpperCase()
  return (status !== '' && status !== 'OK') || problemNumber(d) !== null
}

function dateMs(d: DriverDevice): number {
  const parsed = Date.parse(String(devDateValue(d) ?? ''))
  return Number.isNaN(parsed) ? 0 : parsed
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })

function compare(a: DriverDevice, b: DriverDevice): number {
  switch (sortKey.value) {
    case 'name':
      return collator.compare(devName(a), devName(b))
    case 'status':
      return collator.compare(devStatus(a), devStatus(b))
    case 'problem': {
      const pa = problemNumber(a)
      const pb = problemNumber(b)
      if (pa === null && pb === null) return 0
      if (pa === null) return 1
      if (pb === null) return -1
      return pa - pb
    }
    case 'version':
      return collator.compare(devVersion(a), devVersion(b))
    case 'date':
      return dateMs(a) - dateMs(b)
  }
}

const sortedDevices = computed(() => {
  const list = [...props.devices]
  list.sort((a, b) => (sortDir.value === 'asc' ? compare(a, b) : -compare(a, b)))
  return list
})
</script>

<template>
  <div class="card maintenance-table">
    <h3>
      ไดรเวอร์ ({{ counts.total }})
      <span class="muted small counts">ok {{ counts.ok }} · issues {{ counts.issues }}</span>
      <span class="issues-live" role="status" aria-live="polite">
        <span v-if="counts.issues > 0" class="badge high">{{ counts.issues }} issues</span>
      </span>
    </h3>

    <div v-if="devices.length" class="table-wrap">
      <table>
        <colgroup>
          <col v-for="col in columns" :key="col.key" :class="col.colClass" />
        </colgroup>
        <thead>
          <tr>
            <th v-for="col in columns" :key="col.key" :class="col.colClass" :aria-sort="ariaSort(col.key)">
              <button
                type="button"
                class="sort-btn"
                :class="{ active: sortKey === col.key }"
                @click="toggleSort(col.key)"
              >
                <span>{{ col.label }}</span>
                <span class="sort-indicator" aria-hidden="true">
                  {{ sortKey === col.key ? (sortDir === 'asc' ? '▲' : '▼') : '↕' }}
                </span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(d, i) in sortedDevices" :key="i" :class="{ 'row-issue': isIssue(d) }">
            <td class="name-cell">
              <span class="text-truncate" v-auto-tip>{{ devName(d) }}</span>
            </td>
            <td>
              <span class="sig-badge" :class="isIssue(d) ? 'warn' : 'ok'">{{ devStatus(d) }}</span>
            </td>
            <td class="problem-cell" :class="{ 'has-error': devError(d) }">
              <span class="text-truncate" v-auto-tip>{{ problemLabel(d) }}</span>
            </td>
            <td class="mono">
              <span class="text-truncate" v-auto-tip>{{ devVersion(d) }}</span>
            </td>
            <td class="mono">
              <span class="text-truncate" v-auto-tip>{{ devDate(d) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else-if="scanning" class="muted">กำลังสแกนไดรเวอร์…</p>
    <p v-else class="muted">ยังไม่มีข้อมูลไดรเวอร์ — กดปุ่มสแกนเพื่อเริ่ม</p>
  </div>
</template>

<style scoped>
h3 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.counts { font-weight: 500; text-transform: none; letter-spacing: 0; }
.issues-live { display: inline-flex; align-items: center; min-height: 1px; }

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
  padding: 0;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
}
tbody tr:hover { background: rgba(124, 156, 255, 0.05); }
tbody tr.row-issue { background: rgba(255, 107, 107, 0.06); }

.sort-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  padding: 7px 10px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.sort-btn:hover { color: var(--text); }
.sort-btn.active { color: var(--accent); }
.sort-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.sort-indicator { font-size: 9px; opacity: 0.7; }

.c-name { width: 34%; }
.c-status { width: 10%; }
.c-problem { width: 8%; }
.c-version { width: 26%; }
.c-date { width: 22%; }

.num { font-variant-numeric: tabular-nums; }
.mono, .name-cell, .problem-cell {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
}
.text-truncate { display: block; min-width: 0; }
.problem-cell.has-error { color: var(--bad); }

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
