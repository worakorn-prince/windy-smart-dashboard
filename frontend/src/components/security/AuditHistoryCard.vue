<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useSecurityStore } from '@/stores/security'
import type { PersistedSecurityEvent } from '@/stores/security'

const store = useSecurityStore()

const LIMIT = 20

const loading = ref(false)
const saving = ref(false)
const running = ref(false)
const error = ref('')
const notice = ref('')
const enabled = ref(false)
const intervalHours = ref(24)

const schedule = computed(() => store.auditSchedule)

onMounted(() => {
  refresh()
})

async function refresh() {
  loading.value = true
  error.value = ''
  const [scheduleRes, listRes] = await Promise.all([
    store.loadAuditSchedule(),
    store.loadScheduledAudits(LIMIT),
  ])
  loading.value = false
  if (!scheduleRes.ok) error.value = scheduleRes.reason || 'Failed to load schedule'
  else if (!listRes.ok) error.value = listRes.reason || 'Failed to load audit history'
  syncForm()
}

function syncForm() {
  const current = store.auditSchedule
  if (!current) return
  enabled.value = current.enabled
  intervalHours.value = current.intervalHours
}

async function onSave() {
  const hours = Number(intervalHours.value)
  if (!Number.isFinite(hours) || hours < 0.5 || hours > 168) {
    error.value = 'Interval must be between 0.5 and 168 hours'
    return
  }
  saving.value = true
  error.value = ''
  notice.value = ''
  const res = await store.saveAuditSchedule({ enabled: enabled.value, intervalHours: hours })
  saving.value = false
  if (!res.ok) {
    error.value = res.reason || 'Failed to save schedule'
    return
  }
  notice.value = 'Schedule saved'
  syncForm()
}

async function onRunNow() {
  running.value = true
  error.value = ''
  notice.value = ''
  const res = await store.runScheduledAudit()
  if (!res.ok) {
    running.value = false
    error.value = res.reason || 'Audit failed'
    return
  }
  await store.loadScheduledAudits(LIMIT)
  running.value = false
  notice.value = res.skipped === 'in_flight'
    ? 'An audit is already running — this request was skipped'
    : 'Audit completed and stored'
}

function formatTs(ts: string | null | undefined): string {
  if (!ts) return '—'
  const d = new Date(ts)
  return isNaN(d.getTime()) ? ts : d.toLocaleString()
}

function formatNextDue(value: number | null | undefined): string {
  if (!value || !Number.isFinite(value)) return '—'
  const d = new Date(value * 1000)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

function riskLabel(row: PersistedSecurityEvent): string {
  const label = row.detail?.risk_label
  return typeof label === 'string' && label ? label : '—'
}

function riskClass(row: PersistedSecurityEvent): string {
  return riskLabel(row).toLowerCase()
}

function findingsCount(row: PersistedSecurityEvent): number {
  const value = row.detail?.findings_count
  return typeof value === 'number' ? value : 0
}

function topFinding(row: PersistedSecurityEvent): string {
  const titles = row.detail?.top_findings
  if (!Array.isArray(titles) || titles.length === 0) return '—'
  return String(titles[0])
}
</script>

<template>
  <div class="card audit-history-card">
    <h3>Scheduled Audit</h3>
    <p class="muted small">
      Runs the full audit on a timer and stores each result. Off by default because the
      audit is heavy (WMI/PowerShell).
    </p>

    <div class="controls">
      <label class="toggle small">
        <input v-model="enabled" type="checkbox" :disabled="loading || saving" />
        <span>Enabled</span>
      </label>
      <label class="interval small">
        <span>Every</span>
        <input
          v-model.number="intervalHours"
          type="number"
          min="0.5"
          max="168"
          step="0.5"
          :disabled="loading || saving"
        />
        <span>hours</span>
      </label>
      <button class="primary" :disabled="loading || saving" @click="onSave">
        {{ saving ? 'Saving…' : 'Save' }}
      </button>
      <button :disabled="running" @click="onRunNow">
        {{ running ? 'Running…' : 'Run now' }}
      </button>
    </div>

    <div class="meta muted small">
      <span>Last run: {{ formatTs(schedule?.last_run) }}</span>
      <span>Next due: {{ formatNextDue(schedule?.next_due) }}</span>
    </div>

    <p v-if="error" class="error small">{{ error }}</p>
    <p v-else-if="notice" class="notice small">{{ notice }}</p>

    <div v-if="store.scheduledAudits.length" class="table-wrap">
      <table>
        <thead>
          <tr><th>Time</th><th>Risk</th><th>Findings</th><th>Top finding</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in store.scheduledAudits" :key="row.id">
            <td class="small nowrap">{{ formatTs(row.ts) }}</td>
            <td class="small nowrap">
              <span class="score">{{ row.detail?.riskscore ?? '—' }}</span>
              <span class="badge" :class="riskClass(row)">{{ riskLabel(row) }}</span>
            </td>
            <td class="small">{{ findingsCount(row) }}</td>
            <td class="small detail">{{ topFinding(row) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted small">No scheduled audit results yet.</p>
  </div>
</template>

<style scoped>
.audit-history-card { grid-column: span 2; }
.controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin: 10px 0; }
.toggle { display: flex; gap: 6px; align-items: center; }
.interval { display: flex; gap: 6px; align-items: center; }
.interval input {
  width: 72px; padding: 4px 6px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--panel-2); color: var(--text);
}
.meta { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }
.error { color: var(--bad); }
.notice { color: var(--good); }
.table-wrap { max-height: 320px; overflow-y: auto; }
.nowrap { white-space: nowrap; }
.detail { overflow-wrap: anywhere; }
.score { font-weight: 700; margin-right: 8px; }
.badge {
  padding: 1px 8px; border-radius: 10px; font-size: 10px;
  font-weight: 700; text-transform: uppercase; background: var(--panel-2);
}
.badge.low { background: var(--good); color: #082; }
.badge.medium { background: var(--warn); color: #530; }
.badge.high { background: var(--bad); color: #fff; }
.badge.critical { background: var(--crit); color: #fff; }
table { width: 100%; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--border); }
th { font-size: 11px; color: var(--muted); text-transform: uppercase; }
</style>
