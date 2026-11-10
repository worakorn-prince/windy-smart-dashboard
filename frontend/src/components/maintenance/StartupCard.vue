<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

interface StartupItem {
  id: string
  name: string
  command: string
  location: string
  enabled: boolean
  writable: boolean
  backupStale: boolean
}

const ADMIN_TOKEN_KEY = 'dashboard:adminToken'
const CONFIRM_PHRASE = 'startup'

const items = ref<StartupItem[]>([])
const loading = ref(false)
const busy = ref('')
const error = ref('')
const notice = ref('')
const scannedAt = ref('')

const confirmOpen = ref(false)
const confirmText = ref('')
const pending = ref<StartupItem | null>(null)
const confirmOk = computed(() => confirmText.value.trim() === CONFIRM_PHRASE)

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

function normalize(body: unknown): StartupItem[] {
  const rows = (body as { items?: unknown } | null)?.items
  if (!Array.isArray(rows)) return []
  return rows
    .filter((row): row is Record<string, unknown> => !!row && typeof row === 'object')
    .map((row) => ({
      id: String(row.id ?? ''),
      name: String(row.name ?? ''),
      command: String(row.command ?? ''),
      location: String(row.location ?? ''),
      enabled: row.enabled === true,
      writable: row.writable === true,
      backupStale: row.backup_stale === true,
    }))
    .filter((row) => row.id.length > 0 && row.name.length > 0)
}

function formatScannedAt(value: string): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

function notWritableHint(item: StartupItem): string {
  return item.writable
    ? item.enabled
      ? 'ปิดโปรแกรมนี้ (มี backup ก่อนลบ)'
      : 'เปิดโปรแกรมนี้กลับมา'
    : 'ตำแหน่ง startup-folder แก้ไขไม่ได้ (เปิด/ปิดเองที่โฟลเดอร์ Startup)'
}

async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/maintenance/startup', {
      headers: authHeaders(),
      cache: 'no-store',
    })
    const body = await readBody(response)
    if (!response.ok) {
      throw new Error(errorDetail(body, `โหลดรายการ startup ไม่สำเร็จ (HTTP ${response.status})`))
    }
    items.value = normalize(body)
    scannedAt.value = String((body as { scannedAt?: unknown } | null)?.scannedAt ?? '')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'โหลดรายการ startup ไม่สำเร็จ'
  } finally {
    loading.value = false
  }
}

async function toggle(item: StartupItem, enabled: boolean) {
  if (busy.value) return
  busy.value = item.id
  error.value = ''
  notice.value = ''
  try {
    const response = await fetch('/api/maintenance/startup/toggle', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ id: item.id, enabled, confirm: CONFIRM_PHRASE }),
    })
    const body = await readBody(response)
    if (!response.ok) {
      throw new Error(
        errorDetail(
          body,
          `${enabled ? 'เปิด' : 'ปิด'}รายการ startup ไม่สำเร็จ (HTTP ${response.status})`,
        ),
      )
    }
    notice.value = `${enabled ? 'เปิด' : 'ปิด'} "${item.name}" เรียบร้อย`
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'แก้ไขรายการ startup ไม่สำเร็จ'
  } finally {
    busy.value = ''
  }
}

function askDisable(item: StartupItem) {
  if (busy.value || !item.writable || !item.enabled) return
  pending.value = item
  confirmText.value = ''
  confirmOpen.value = true
}

function closeConfirm() {
  if (busy.value) return
  confirmOpen.value = false
  confirmText.value = ''
  pending.value = null
}

async function confirmDisable() {
  if (!confirmOk.value || busy.value) return
  const target = pending.value
  confirmOpen.value = false
  confirmText.value = ''
  pending.value = null
  if (target) await toggle(target, false)
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="card startup-card" data-testid="startup-card">
    <h3>
      โปรแกรมที่เปิดพร้อม Windows ({{ items.length }})
      <button class="btn tiny" :disabled="loading || !!busy" @click="load">
        {{ loading ? 'กำลังโหลด…' : 'รีเฟรช' }}
      </button>
    </h3>

    <p class="muted small">
      อ่านจาก HKCU/HKLM Run, RunOnce และโฟลเดอร์ Startup — การปิดจะสำรองค่าจริงไว้ก่อนลบ
      และกดเปิดกลับคืนได้ทุกเมื่อ (พิมพ์ <span class="kbd">startup</span> เพื่อยืนยัน)
    </p>

    <p v-if="error" class="error-text" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice-text" role="status">{{ notice }}</p>

    <p v-if="loading && !items.length" class="muted small" role="status">กำลังโหลดรายการ startup…</p>
    <p v-else-if="!items.length" class="muted small">ไม่พบโปรแกรมที่เปิดพร้อม Windows</p>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="c-name">ชื่อ</th>
            <th class="c-command">คำสั่ง</th>
            <th class="c-location">ตำแหน่ง</th>
            <th class="c-state">สถานะ</th>
            <th class="c-action">จัดการ</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.id">
            <td class="mono">
              <span class="text-truncate" :title="item.name">{{ item.name }}</span>
            </td>
            <td class="mono">
              <span class="text-truncate" :title="item.command">{{ item.command }}</span>
            </td>
            <td>
              <span class="kbd">{{ item.location }}</span>
            </td>
            <td>
              <span class="state-badge" :class="item.enabled ? 'on' : 'off'">
                {{ item.enabled ? 'เปิด' : 'ปิด' }}
              </span>
              <span
                v-if="item.backupStale"
                class="state-badge stale"
                title="มี entry ค้างในไฟล์ backup แต่ค่ายังอยู่ใน registry — สถานะจริงคือเปิดใช้งาน (backup ไม่ถูกแตะ)"
              >
                backup ค้าง
              </span>
            </td>
            <td class="action-cell">
              <button
                v-if="item.enabled"
                class="btn tiny"
                :disabled="!item.writable || !!busy"
                :title="notWritableHint(item)"
                @click="askDisable(item)"
              >
                {{ busy === item.id ? 'กำลังปิด…' : 'Disable' }}
              </button>
              <button
                v-else
                class="btn tiny"
                :disabled="!item.writable || !!busy"
                :title="notWritableHint(item)"
                @click="toggle(item, true)"
              >
                {{ busy === item.id ? 'กำลังเปิด…' : 'Enable' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="muted small scanned-note">สแกนล่าสุด: {{ formatScannedAt(scannedAt) }}</p>

    <div v-if="confirmOpen" class="modal-backdrop" @click.self="closeConfirm">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="startup-confirm-title">
        <h3 id="startup-confirm-title">ยืนยันการปิดโปรแกรม startup</h3>
        <p class="muted">
          จะสำรองค่าจริงไว้ที่ไฟล์ backup ก่อนลบออกจาก registry และกด Enable กลับคืนได้
          — พิมพ์คำว่า <span class="kbd">startup</span> เพื่อยืนยัน
        </p>
        <p v-if="pending" class="pending-name mono">{{ pending.name }}</p>
        <input
          v-model="confirmText"
          class="confirm-input"
          type="text"
          autocomplete="off"
          spellcheck="false"
          placeholder="startup"
          @keyup.enter="confirmDisable"
        />
        <div class="modal-actions">
          <button class="btn" :disabled="!!busy" @click="closeConfirm">ยกเลิก</button>
          <button class="btn primary" :disabled="!confirmOk || !!busy" @click="confirmDisable">
            {{ busy ? 'กำลังปิด…' : 'ยืนยันปิด' }}
          </button>
        </div>
      </div>
    </div>
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

.table-wrap { overflow-x: auto; overflow-y: auto; max-height: 380px; }

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

.c-name { width: 22%; }
.c-command { width: 38%; }
.c-location { width: 16%; }
.c-state { width: 9%; }
.c-action { width: 15%; }

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
.action-cell { white-space: nowrap; }

.state-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
}
.state-badge.on { background: rgba(95, 217, 124, 0.15); color: var(--good); }
.state-badge.off { background: rgba(255, 215, 95, 0.15); color: var(--warn); }
.state-badge.stale { background: rgba(255, 107, 107, 0.15); color: var(--bad); margin-left: 4px; }

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

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.55);
}
.modal {
  width: 100%;
  max-width: 420px;
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.45);
}
.modal h3 { margin: 0 0 8px; }
.modal p { margin: 0 0 12px; line-height: 1.5; }
.pending-name {
  padding: 6px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
  word-break: break-all;
}
.confirm-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
}
.confirm-input:focus { outline: none; border-color: var(--info); }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.modal-actions .btn { padding: 6px 14px; }
</style>
