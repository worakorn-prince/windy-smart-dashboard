<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

interface PendingReboot {
  pending: boolean
  reasons: string[]
}

interface InstalledUpdate {
  id: string
  description: string
  installedOn: string
}

interface LastScan {
  ts: string
  ok: boolean
  count: number
  titles: string[]
  durationMs: number
}

const ADMIN_TOKEN_KEY = 'dashboard:adminToken'

const REASON_LABEL: Record<string, string> = {
  CBS: 'Component Based Servicing',
  WU: 'Windows Update',
  PendingFileRename: 'Pending file rename operations',
}

const SECTION_LABEL: Record<string, string> = {
  pendingReboot: 'pending reboot',
  installed: 'hotfix',
  lastScan: 'ประวัติการสแกน',
}

const pending = ref<PendingReboot>({ pending: false, reasons: [] })
const installed = ref<InstalledUpdate[]>([])
const lastScan = ref<LastScan | null>(null)
const sectionErrors = ref<{ key: string; label: string; message: string }[]>([])
const scannedAt = ref('')
const loading = ref(false)
const scanning = ref(false)
const loaded = ref(false)
const error = ref('')
const notice = ref('')

const busy = computed(() => loading.value || scanning.value)
const hasErrors = computed(() => sectionErrors.value.length > 0)

function adminToken(): string {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'windy-dashboard',
  }
  const token = adminToken()
  if (token) headers['X-Admin-Token'] = token
  return headers
}

function errorDetail(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (detail && typeof detail === 'object') {
    const record = detail as { code?: unknown; text?: unknown; hint?: unknown }
    const code = String(record.code ?? '').trim()
    const text = String(record.text ?? '').trim()
    const hint = String(record.hint ?? '').trim()
    const head = [code, text].filter(Boolean).join(': ')
    if (head && hint) return `${head} — ${hint}`
    if (head) return head
    if (hint) return hint
  }
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  return fallback
}

async function readBody(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function normalizePending(value: unknown): PendingReboot {
  const record = (value ?? {}) as Record<string, unknown>
  const reasons = Array.isArray(record.reasons)
    ? record.reasons.map((reason) => String(reason ?? '')).filter((reason) => reason.length > 0)
    : []
  return { pending: record.pending === true, reasons }
}

function normalizeInstalled(value: unknown): InstalledUpdate[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((row): row is Record<string, unknown> => !!row && typeof row === 'object')
    .map((row) => ({
      id: String(row.id ?? ''),
      description: String(row.description ?? ''),
      installedOn: String(row.installedOn ?? ''),
    }))
    .filter((row) => row.id.length > 0)
}

function normalizeLastScan(value: unknown): LastScan | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const count = Number(row.count ?? 0)
  const durationMs = Number(row.durationMs ?? 0)
  const titles = Array.isArray(row.titles) ? row.titles.map((title) => String(title ?? '')) : []
  return {
    ts: String(row.ts ?? ''),
    ok: row.ok === true,
    count: Number.isFinite(count) ? count : 0,
    titles: titles.filter((title) => title.length > 0),
    durationMs: Number.isFinite(durationMs) ? durationMs : 0,
  }
}

function normalizeErrors(value: unknown): { key: string; label: string; message: string }[] {
  if (!value || typeof value !== 'object') return []
  const out: { key: string; label: string; message: string }[] = []
  for (const [key, message] of Object.entries(value as Record<string, unknown>)) {
    const text = String(message ?? '').trim()
    if (!text) continue
    out.push({ key, label: SECTION_LABEL[key] ?? key, message: text })
  }
  return out
}

function formatDateTime(value: string): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

function reasonLabel(reason: string): string {
  return REASON_LABEL[reason] ?? reason
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/maintenance/windows-update', {
      headers: authHeaders(),
      cache: 'no-store',
    })
    const body = await readBody(response)
    if (!response.ok) {
      throw new Error(errorDetail(body, `โหลดสถานะ Windows Update ไม่สำเร็จ (HTTP ${response.status})`))
    }
    const payload = (body ?? {}) as Record<string, unknown>
    pending.value = normalizePending(payload.pendingReboot)
    installed.value = normalizeInstalled(payload.installed)
    lastScan.value = normalizeLastScan(payload.lastScan)
    sectionErrors.value = normalizeErrors(payload.errors)
    scannedAt.value = String(payload.scannedAt ?? '')
    loaded.value = true
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'โหลดสถานะ Windows Update ไม่สำเร็จ'
  } finally {
    loading.value = false
  }
}

async function scanNow() {
  if (busy.value) return
  scanning.value = true
  error.value = ''
  notice.value = ''
  try {
    const response = await fetch('/api/maintenance/windows-update/scan', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({}),
    })
    const body = await readBody(response)
    if (!response.ok) {
      throw new Error(errorDetail(body, `สแกน Windows Update ไม่สำเร็จ (HTTP ${response.status})`))
    }
    const result = (body as { result?: { updateCount?: unknown } } | null)?.result
    const count = Number(result?.updateCount ?? 0)
    notice.value = `สแกนเสร็จแล้ว — พบ ${Number.isFinite(count) ? count : 0} อัปเดตที่ยังไม่ได้ติดตั้ง`
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'สแกน Windows Update ไม่สำเร็จ'
  } finally {
    scanning.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="card windows-update-card" data-testid="windows-update-card">
    <h3>
      Windows Update &amp; Pending Reboot
      <span class="head-actions">
        <button class="btn tiny" :disabled="busy" @click="load">
          {{ loading ? 'กำลังโหลด…' : 'รีเฟรช' }}
        </button>
        <button class="btn tiny primary" :disabled="busy" @click="scanNow">
          {{ scanning ? 'กำลังสแกน…' : 'Scan now' }}
        </button>
      </span>
    </h3>

    <p class="muted small">
      อ่านจาก registry (CBS, Windows Update, PendingFileRenameOperations), Hotfix ล่าสุด 5 รายการ
      และผล <span class="kbd">wu-scan</span> ครั้งล่าสุดจากประวัติ — การสแกนเป็นแบบอ่านเท่านั้น ไม่ติดตั้งอะไร
    </p>

    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice-text" role="status">{{ notice }}</p>

    <div class="pending-row">
      <span
        class="state-badge"
        :class="pending.pending ? 'bad' : 'good'"
        data-testid="pending-reboot-badge"
      >
        {{ pending.pending ? 'มี pending reboot' : 'ไม่มี pending reboot' }}
      </span>
      <span v-if="pending.reasons.length" class="reason-list">
        <span
          v-for="reason in pending.reasons"
          :key="reason"
          class="kbd reason-chip"
          :title="reasonLabel(reason)"
        >
          {{ reason }}
        </span>
      </span>
      <span v-else class="muted small">ไม่พบสาเหตุที่ต้องรีสตาร์ท</span>
    </div>

    <div v-if="hasErrors" class="partial-errors">
      <p v-for="item in sectionErrors" :key="item.key" class="muted small" role="status">
        ⚠ อ่านข้อมูล {{ item.label }} ไม่ได้: {{ item.message }}
      </p>
    </div>

    <p v-if="!loaded && loading" class="muted small" role="status">กำลังโหลดสถานะ Windows Update…</p>

    <div class="grid-2">
      <section>
        <h4>Hotfix ล่าสุด ({{ installed.length }})</h4>
        <p v-if="!installed.length" class="muted small">ไม่พบข้อมูล hotfix</p>
        <ul v-else class="hotfix-list">
          <li v-for="item in installed" :key="item.id">
            <span class="mono kbd hotfix-id">{{ item.id }}</span>
            <span class="hotfix-desc text-truncate" :title="item.description">
              {{ item.description || '—' }}
            </span>
            <span class="muted small hotfix-date">{{ item.installedOn || '—' }}</span>
          </li>
        </ul>
      </section>

      <section>
        <h4>ผลสแกนล่าสุด (wu-scan)</h4>
        <p v-if="!lastScan" class="muted small">ยังไม่มีประวัติการสแกน</p>
        <template v-else>
          <p class="small scan-meta">
            {{ formatDateTime(lastScan.ts) }} · {{ lastScan.count }} รายการ · {{ lastScan.durationMs }} ms
            <span class="state-badge" :class="lastScan.ok ? 'good' : 'bad'">
              {{ lastScan.ok ? 'สำเร็จ' : 'ล้มเหลว' }}
            </span>
          </p>
          <ul v-if="lastScan.titles.length" class="scan-titles">
            <li
              v-for="(title, index) in lastScan.titles"
              :key="`${index}-${title}`"
              class="mono small text-truncate"
              v-auto-tip
            >
              {{ title }}
            </li>
          </ul>
          <p v-else class="muted small">ไม่มีรายการอัปเดตที่ค้างอยู่</p>
        </template>
      </section>
    </div>

    <p class="muted small scanned-note">อ่านสถานะเมื่อ: {{ formatDateTime(scannedAt) }}</p>
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

h4 {
  margin: 0 0 6px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
}

.head-actions { display: flex; gap: 6px; flex-wrap: wrap; }

.btn {
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  border-radius: 6px;
  cursor: pointer;
  font-weight: 600;
}
.btn.tiny { padding: 3px 10px; font-size: 11px; line-height: 1.4; }
.btn.primary { border-color: var(--accent); color: var(--accent); }
.btn:hover:not(:disabled) { background: var(--border); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.pending-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 4px 0 10px;
}
.reason-list { display: flex; gap: 6px; flex-wrap: wrap; }
.reason-chip { font-size: 10.5px; }

.state-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
}
.state-badge.good { background: rgba(95, 217, 124, 0.15); color: var(--good); }
.state-badge.bad { background: rgba(255, 107, 107, 0.15); color: var(--bad); }

.grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
  margin-top: 6px;
}

.hotfix-list, .scan-titles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hotfix-list li {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
}
.hotfix-id { font-size: 10.5px; }
.hotfix-date { white-space: nowrap; }

.scan-meta { margin: 0 0 6px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
}
.text-truncate {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.partial-errors {
  margin: 4px 0 8px;
  padding: 6px 9px;
  border: 1px dashed var(--warn);
  border-radius: 6px;
}
.partial-errors p { margin: 0; }

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
.scanned-note { margin: 10px 0 0; }
</style>
