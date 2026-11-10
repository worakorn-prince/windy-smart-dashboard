<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSecurityStore } from '@/stores/security'

interface ReportItem {
  name: string
  size: number
  mtime: number
}

interface ReportSchedule {
  enabled: boolean
  intervalHours: number
  days: number
  nextRun: number | null
}

const MIN_INTERVAL_HOURS = 0.25
const MAX_INTERVAL_HOURS = 168

const security = useSecurityStore()

const reports = ref<ReportItem[]>([])
const loading = ref(false)
const busy = ref<0 | 1 | 7>(0)
const downloading = ref('')
const error = ref('')
const notice = ref('')

const schedule = ref<ReportSchedule>({
  enabled: true,
  intervalHours: 24,
  days: 1,
  nextRun: null,
})
const scheduleLoading = ref(false)
const scheduleSaving = ref(false)
const scheduleError = ref('')
const scheduleNotice = ref('')

function authHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Admin-Token': security.adminToken,
  }
}

async function responseError(response: Response, fallback: string): Promise<string> {
  if (response.status === 401) {
    return 'Unauthorized (401): admin token missing or invalid — set it in Security Settings'
  }
  if (response.status === 403) {
    return 'Forbidden (403): reports are allowed from localhost only'
  }
  const body = await response.json().catch(() => null)
  const detail = body && typeof body.detail === 'string' ? body.detail : ''
  return detail ? `${fallback}: ${detail}` : `${fallback} (HTTP ${response.status})`
}

function normalizeReports(body: unknown): ReportItem[] {
  const rows = Array.isArray(body)
    ? body
    : body && typeof body === 'object' && Array.isArray((body as { reports?: unknown }).reports)
      ? ((body as { reports: unknown[] }).reports)
      : []
  return rows
    .filter((row): row is Record<string, unknown> => !!row && typeof row === 'object')
    .map((row) => ({
      name: String(row.name ?? ''),
      size: Number(row.size ?? 0),
      mtime: Number(row.mtime ?? 0),
    }))
    .filter((row) => row.name.length > 0)
    .sort((a, b) => b.mtime - a.mtime)
}

function formatSize(size: number): string {
  const amount = Number(size)
  if (!Number.isFinite(amount) || amount < 0) return '—'
  if (amount < 1024) return `${amount} B`
  if (amount < 1024 ** 2) return `${(amount / 1024).toFixed(1)} KB`
  return `${(amount / 1024 ** 2).toFixed(2)} MB`
}

function formatTime(mtime: number): string {
  const numeric = Number(mtime)
  if (!Number.isFinite(numeric)) return '—'
  const parsed = new Date(numeric > 1e12 ? numeric : numeric * 1000)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

function formatNextRun(nextRun: number | null): string {
  if (nextRun === null || nextRun === undefined) return '—'
  return formatTime(Number(nextRun))
}

function normalizeSchedule(body: unknown): ReportSchedule {
  const record = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>
  const interval = Number(record.intervalHours)
  const days = Number(record.days)
  const nextRun = record.nextRun === null || record.nextRun === undefined ? null : Number(record.nextRun)
  return {
    enabled: record.enabled === true,
    intervalHours: Number.isFinite(interval) ? interval : 24,
    days: days === 7 ? 7 : 1,
    nextRun: nextRun !== null && Number.isFinite(nextRun) ? nextRun : null,
  }
}

async function loadSchedule() {
  scheduleLoading.value = true
  scheduleError.value = ''
  try {
    const response = await fetch('/api/reports/schedule', { headers: authHeaders(), cache: 'no-store' })
    if (!response.ok) {
      throw new Error(await responseError(response, 'โหลดตารางรายงานไม่สำเร็จ'))
    }
    schedule.value = normalizeSchedule(await response.json())
  } catch (err) {
    scheduleError.value = err instanceof Error ? err.message : 'โหลดตารางรายงานไม่สำเร็จ'
  } finally {
    scheduleLoading.value = false
  }
}

async function saveSchedule() {
  if (scheduleSaving.value) return
  const interval = Number(schedule.value.intervalHours)
  if (!Number.isFinite(interval) || interval < MIN_INTERVAL_HOURS || interval > MAX_INTERVAL_HOURS) {
    scheduleError.value = `Interval ต้องอยู่ระหว่าง ${MIN_INTERVAL_HOURS}–${MAX_INTERVAL_HOURS} ชั่วโมง`
    return
  }
  scheduleSaving.value = true
  scheduleError.value = ''
  scheduleNotice.value = ''
  try {
    const response = await fetch('/api/reports/schedule', {
      method: 'PUT',
      headers: { ...authHeaders(), 'X-Requested-With': 'windy-dashboard' },
      body: JSON.stringify({
        enabled: schedule.value.enabled,
        intervalHours: interval,
        days: schedule.value.days === 7 ? 7 : 1,
      }),
    })
    if (!response.ok) {
      throw new Error(await responseError(response, 'บันทึกตารางรายงานไม่สำเร็จ'))
    }
    schedule.value = normalizeSchedule(await response.json())
    scheduleNotice.value = schedule.value.enabled
      ? `บันทึกแล้ว — รายงานถัดไป ${formatNextRun(schedule.value.nextRun)}`
      : 'บันทึกแล้ว — ปิดการสร้างรายงานอัตโนมัติ'
  } catch (err) {
    scheduleError.value = err instanceof Error ? err.message : 'บันทึกตารางรายงานไม่สำเร็จ'
  } finally {
    scheduleSaving.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/reports', { headers: authHeaders(), cache: 'no-store' })
    if (!response.ok) {
      throw new Error(await responseError(response, 'โหลดรายการรายงานไม่สำเร็จ'))
    }
    reports.value = normalizeReports(await response.json())
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'โหลดรายการรายงานไม่สำเร็จ'
  } finally {
    loading.value = false
  }
}

async function generate(days: 1 | 7) {
  if (busy.value) return
  busy.value = days
  error.value = ''
  notice.value = ''
  try {
    const response = await fetch('/api/reports/generate', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ days }),
    })
    if (!response.ok) {
      throw new Error(await responseError(response, 'สร้างรายงานไม่สำเร็จ'))
    }
    const body = (await response.json()) as { name?: string }
    notice.value = `สร้างรายงานแล้ว: ${body.name ?? ''}`
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'สร้างรายงานไม่สำเร็จ'
  } finally {
    busy.value = 0
  }
}

async function download(name: string) {
  if (downloading.value) return
  downloading.value = name
  error.value = ''
  try {
    const response = await fetch(`/api/reports/${encodeURIComponent(name)}`, {
      headers: authHeaders(),
    })
    if (!response.ok) {
      throw new Error(await responseError(response, 'ดาวน์โหลดรายงานไม่สำเร็จ'))
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = name
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'ดาวน์โหลดรายงานไม่สำเร็จ'
  } finally {
    downloading.value = ''
  }
}

onMounted(() => {
  void load()
  void loadSchedule()
})
</script>

<template>
  <div class="card reports-card">
    <h3>
      รายงานตามกำหนด (Scheduled reports)
      <button class="btn tiny" :disabled="loading || busy !== 0" @click="load">
        {{ loading ? 'กำลังโหลด…' : 'รีเฟรช' }}
      </button>
    </h3>

    <p class="muted small">
      สร้างรายงาน HTML ไฟล์เดียวจากข้อมูลจริง (สรุป metrics, security events, สุขภาพดิสก์, top processes)
    </p>

    <section class="schedule" :aria-busy="scheduleLoading">
      <h4>Schedule</h4>
      <div class="schedule-grid">
        <label class="schedule-field">
          <span>Enabled</span>
          <input
            v-model="schedule.enabled"
            type="checkbox"
            :disabled="scheduleLoading || scheduleSaving"
          />
        </label>
        <label class="schedule-field">
          <span>Interval (hours)</span>
          <input
            v-model.number="schedule.intervalHours"
            type="number"
            min="0.25"
            max="168"
            step="0.25"
            :disabled="scheduleLoading || scheduleSaving"
          />
        </label>
        <label class="schedule-field">
          <span>Days</span>
          <select v-model.number="schedule.days" :disabled="scheduleLoading || scheduleSaving">
            <option :value="1">Daily (1 วัน)</option>
            <option :value="7">Weekly (7 วัน)</option>
          </select>
        </label>
        <button class="btn" :disabled="scheduleLoading || scheduleSaving" @click="saveSchedule">
          {{ scheduleSaving ? 'กำลังบันทึก…' : 'Save' }}
        </button>
      </div>
      <p class="muted small">รอบถัดไป: {{ formatNextRun(schedule.nextRun) }}</p>
      <p v-if="scheduleError" class="error-text" role="alert">{{ scheduleError }}</p>
      <p v-if="scheduleNotice" class="notice-text" role="status">{{ scheduleNotice }}</p>
    </section>

    <div class="action-list">
      <button :disabled="busy !== 0" @click="generate(1)">
        {{ busy === 1 ? 'กำลังสร้าง…' : 'Generate daily' }}
      </button>
      <button :disabled="busy !== 0" @click="generate(7)">
        {{ busy === 7 ? 'กำลังสร้าง…' : 'Generate weekly' }}
      </button>
    </div>

    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice-text" role="status">{{ notice }}</p>

    <p v-if="loading && !reports.length" class="muted small" role="status">กำลังโหลดรายงาน…</p>
    <p v-else-if="!reports.length" class="muted small">ยังไม่มีรายงาน</p>
    <ul v-else class="report-list">
      <li v-for="report in reports" :key="report.name" class="report-row">
        <div class="report-meta">
          <span class="report-name" :title="report.name">{{ report.name }}</span>
          <span class="muted small">{{ formatSize(report.size) }} · {{ formatTime(report.mtime) }}</span>
        </div>
        <a
          class="download-link"
          :href="`/api/reports/${encodeURIComponent(report.name)}`"
          :aria-busy="downloading === report.name"
          @click.prevent="download(report.name)"
        >
          {{ downloading === report.name ? 'กำลังดาวน์โหลด…' : 'ดาวน์โหลด' }}
        </a>
      </li>
    </ul>

    <p class="muted small retention-note">เก็บรายงานล่าสุดสูงสุด 30 ไฟล์ (prune อัตโนมัติ)</p>
  </div>
</template>

<style scoped>
h3 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.btn,
.action-list button {
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}
.btn.tiny { padding: 3px 10px; font-size: 11px; line-height: 1.4; }
.btn:hover:not(:disabled),
.action-list button:hover:not(:disabled) { background: var(--border); }
.btn:disabled,
.action-list button:disabled { opacity: 0.5; cursor: not-allowed; }

.action-list { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 4px; }
.action-list button { padding: 6px 14px; font-size: 12px; }

.schedule {
  margin: 10px 0 0;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
}
.schedule h4 {
  margin: 0 0 8px;
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}
.schedule-grid {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
.schedule-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11.5px;
  color: var(--muted);
}
.schedule-field input[type='number'],
.schedule-field select {
  min-width: 110px;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--text);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.schedule-field input[type='checkbox'] {
  width: 16px;
  height: 16px;
  margin: 2px 0;
}
.schedule-grid .btn { padding: 6px 14px; font-size: 12px; }
.schedule p { margin: 8px 0 0; }

.report-list {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.report-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
}
.report-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.report-name {
  font-size: 11.5px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.download-link {
  color: var(--info);
  font-size: 11.5px;
  font-weight: 600;
  white-space: nowrap;
  text-decoration: none;
}
.download-link:hover { text-decoration: underline; }

.error-text {
  margin: 8px 0 0;
  padding: 6px 9px;
  border: 1px solid var(--bad);
  border-radius: 6px;
  color: var(--bad);
  font-size: 11.5px;
}
.notice-text {
  margin: 8px 0 0;
  padding: 6px 9px;
  border: 1px solid var(--info);
  border-radius: 6px;
  color: var(--info);
  font-size: 11.5px;
}
.retention-note { margin: 10px 0 0; }
</style>
