<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useMaintenanceStore } from '@/stores/maintenance'
import { formatBytes, formatPercent } from '@/utils/format'
import MaintenanceAdminBanner from '@/components/maintenance/MaintenanceAdminBanner.vue'
import MaintenancePanel from '@/components/maintenance/MaintenancePanel.vue'
import MaintenanceTable from '@/components/maintenance/MaintenanceTable.vue'
import MaintenanceHistory from '@/components/maintenance/MaintenanceHistory.vue'
import DiskHealthCard from '@/components/maintenance/DiskHealthCard.vue'
import ReportsCard from '@/components/maintenance/ReportsCard.vue'

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

function pickNumber(o: Record<string, any>, keys: string[]): number | null {
  for (const key of keys) {
    const raw = o[key]
    if (raw === null || raw === undefined || raw === '') continue
    const n = Number(raw)
    if (Number.isFinite(n)) return n
  }
  return null
}

function bytesOf(
  o: Record<string, any>,
  byteKeys: string[],
  gbKeys: string[],
  genericKeys: string[],
): number | null {
  const direct = pickNumber(o, byteKeys)
  if (direct !== null) return direct
  const gb = pickNumber(o, gbKeys)
  if (gb !== null) return gb * 1024 ** 3
  const generic = pickNumber(o, genericKeys)
  if (generic === null) return null
  return generic >= 1048576 ? generic : generic * 1024 ** 3
}

function percentText(part: number | null, total: number | null, rawPct: number | null): string {
  if (rawPct !== null) return formatPercent(rawPct, 100)
  if (part !== null && total !== null) return formatPercent(part, total)
  return ''
}

function memoryText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value !== 'object') return String(value)
  const o = value as Record<string, any>
  const total = bytesOf(o, ['totalBytes', 'total_bytes'], ['totalGB', 'TotalGB', 'totalGb', 'TotalGb'], ['total', 'Total'])
  const used = bytesOf(o, ['usedBytes', 'used_bytes'], ['usedGB', 'UsedGB', 'usedGb'], ['used', 'Used'])
  const free = bytesOf(
    o,
    ['freeBytes', 'free_bytes', 'availableBytes', 'available_bytes'],
    ['freeGB', 'FreeGB', 'availableGB', 'availableGb'],
    ['free', 'Free', 'available'],
  )
  const usedBytes = used ?? (total !== null && free !== null ? total - free : null)
  const pct = percentText(usedBytes, total, pickNumber(o, ['usedPercent', 'used_pct', 'percent', 'loadPercent']))
  if (total !== null && usedBytes !== null) {
    return `ใช้ ${formatBytes(usedBytes)} / ${formatBytes(total)}${pct ? ` (${pct})` : ''}`
  }
  if (total !== null && free !== null) {
    return `ว่าง ${formatBytes(free)} / ${formatBytes(total)}${pct ? ` (${pct})` : ''}`
  }
  return text(value)
}

function diskText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value !== 'object') return String(value)
  const o = value as Record<string, any>
  const name = o.drive ?? o.name ?? o.letter ?? o.device ?? o.mount ?? ''
  const total = bytesOf(
    o,
    ['totalBytes', 'total_bytes', 'sizeBytes', 'size_bytes'],
    ['totalGB', 'TotalGB', 'sizeGB'],
    ['total', 'Total', 'size'],
  )
  const free = bytesOf(
    o,
    ['freeBytes', 'free_bytes', 'availableBytes', 'available_bytes'],
    ['freeGB', 'FreeGB', 'availableGB', 'availableGb'],
    ['free', 'Free', 'available'],
  )
  const pct = percentText(free, total, pickNumber(o, ['freePercent', 'free_pct']))
  const parts: string[] = []
  if (name) parts.push(String(name))
  if (total !== null && free !== null) parts.push(`ว่าง ${formatBytes(free)} / ${formatBytes(total)}${pct ? ` (${pct})` : ''}`)
  else if (total !== null) parts.push(formatBytes(total))
  return parts.length ? parts.join(' · ') : text(value)
}

function formatDate(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const raw = String(value)
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

const RELAUNCH_POLL_MS = 3000
const RELAUNCH_TIMEOUT_MS = 60000

type RelaunchState = 'idle' | 'scheduled' | 'reconnected' | 'timeout'

const confirmOpen = ref(false)
const confirmText = ref('')
const relaunchState = ref<RelaunchState>('idle')
const confirmOk = computed(() => confirmText.value.trim() === 'relaunch')

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollInFlight = false

const relaunchStatusText = computed(() => {
  switch (relaunchState.value) {
    case 'scheduled':
      return 'scheduled — หน้านี้จะหลุดการเชื่อมต่อ'
    case 'reconnected':
      return 'เชื่อมต่อเซิร์ฟเวอร์ใหม่ได้แล้ว'
    case 'timeout':
      return 'ยังเชื่อมต่อเซิร์ฟเวอร์ไม่ได้ภายใน 60 วินาที'
    default:
      return ''
  }
})

function stopReconnectWatch() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function checkReconnected(deadline: number) {
  if (pollInFlight) return
  pollInFlight = true
  try {
    const resp = await fetch('/api/system', { cache: 'no-store' })
    if (resp.ok) {
      stopReconnectWatch()
      relaunchState.value = 'reconnected'
      await Promise.all([store.loadStatus(), store.loadScan(false)])
      return
    }
  } catch {
    // backend still restarting
  } finally {
    pollInFlight = false
  }
  if (Date.now() >= deadline && relaunchState.value === 'scheduled') {
    stopReconnectWatch()
    relaunchState.value = 'timeout'
    store.error = 'ยังเชื่อมต่อเซิร์ฟเวอร์ไม่ได้ภายใน 60 วินาที — ตรวจสอบว่าเซิร์ฟเวอร์รันอยู่'
  }
}

function startReconnectWatch() {
  stopReconnectWatch()
  const deadline = Date.now() + RELAUNCH_TIMEOUT_MS
  pollTimer = setInterval(() => {
    void checkReconnected(deadline)
  }, RELAUNCH_POLL_MS)
}

function openRelaunch() {
  if (store.busy) return
  if (relaunchState.value !== 'scheduled') relaunchState.value = 'idle'
  confirmText.value = ''
  confirmOpen.value = true
}

function closeRelaunch() {
  if (store.busy === 'relaunch') return
  confirmOpen.value = false
  confirmText.value = ''
}

async function confirmRelaunch() {
  if (!confirmOk.value || store.busy === 'relaunch') return
  const res = await store.runRelaunch()
  confirmOpen.value = false
  confirmText.value = ''
  if (!res) return
  relaunchState.value = 'scheduled'
  startReconnectWatch()
}

async function exportData(kind: 'devices' | 'history', format: 'csv' | 'json') {
  await store.downloadExport(kind, format)
}

onMounted(() => {
  store.loadStatus()
  store.loadScan(false)
})

onUnmounted(stopReconnectWatch)
</script>

<template>
  <div class="maintenance-page">
    <MaintenanceAdminBanner />

    <div v-if="store.error" class="banner error" role="alert">
      <span>{{ store.error }}</span>
      <button class="btn tiny" @click="store.error = ''">ปิด</button>
    </div>
    <div v-if="store.notice" class="banner notice" role="status">
      <span>{{ store.notice }}</span>
      <button class="btn tiny" @click="store.notice = ''">ปิด</button>
    </div>
    <div
      v-if="relaunchStatusText"
      class="banner"
      :class="relaunchState === 'timeout' ? 'error' : 'notice'"
      role="status"
    >
      <span>{{ relaunchStatusText }}</span>
    </div>

    <div class="page-head">
      <h2>
        Maintenance
        <span v-if="store.hasIssues" class="badge high">{{ store.counts.issues }} issues</span>
      </h2>
      <div class="head-actions">
        <button
          :disabled="!!store.busy || relaunchState === 'scheduled'"
          @click="openRelaunch"
        >
          {{ store.busy === 'relaunch' ? 'กำลังสั่งงาน…' : 'รีสตาร์ทบริการ (relaunch)' }}
        </button>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h3>สรุปสถานะระบบ</h3>
        <p v-if="store.loading" class="muted">กำลังโหลดสถานะ…</p>
        <template v-else-if="store.system">
          <div class="row">
            <span class="label">สิทธิ์ผู้ดูแล</span>
            <span class="value">
              <span class="badge" :class="store.isAdmin ? 'low' : 'medium'">
                {{ store.isAdmin ? 'Administrator' : 'Standard user' }}
              </span>
            </span>
          </div>
          <div class="row">
            <span class="label">ระบบปฏิบัติการ</span>
            <span class="value text-truncate" v-auto-tip>{{ text(store.system.os) }}</span>
          </div>
          <div class="row">
            <span class="label">CPU</span>
            <span class="value text-truncate" v-auto-tip>{{ text(store.system.cpu) }}</span>
          </div>
          <div class="row">
            <span class="label">หน่วยความจำ</span>
            <span class="value">{{ memoryText(store.system.memory) }}</span>
          </div>
          <div class="row">
            <span class="label">ดิสก์</span>
            <span class="value">{{ (store.system.disks || []).length }} รายการ</span>
          </div>
          <div v-if="store.system.disks && store.system.disks.length" class="disk-list">
            <span v-for="(disk, i) in store.system.disks" :key="i" class="kbd disk-chip">{{ diskText(disk) }}</span>
          </div>
          <div class="row">
            <span class="label">PowerShell</span>
            <span class="value">{{ text(store.system.psVersion) }}</span>
          </div>
          <div class="row">
            <span class="label">Python</span>
            <span class="value">{{ text(store.system.pythonVersion) }}</span>
          </div>
          <div class="row">
            <span class="label">เก็บข้อมูลเมื่อ</span>
            <span class="value">{{ formatDate(store.system.collectedAt) }}</span>
          </div>
        </template>
        <p v-else class="muted">ยังไม่มีข้อมูลสถานะระบบ</p>
        <button class="btn primary as-button" :disabled="store.loading" @click="store.loadStatus()">รีเฟรชสถานะ</button>
      </div>

      <MaintenancePanel />

      <DiskHealthCard />

      <ReportsCard />

      <div class="card">
        <h3>ส่งออกข้อมูล</h3>
        <p class="muted small">ดาวน์โหลดรายการไดรเวอร์หรือประวัติการบำรุงรักษา</p>
        <div class="action-list">
          <button :disabled="!!store.busy" @click="exportData('devices', 'csv')">Devices CSV</button>
          <button :disabled="!!store.busy" @click="exportData('devices', 'json')">Devices JSON</button>
          <button :disabled="!!store.busy" @click="exportData('history', 'csv')">History CSV</button>
          <button :disabled="!!store.busy" @click="exportData('history', 'json')">History JSON</button>
        </div>
      </div>
    </div>

    <div class="full-row">
      <MaintenanceTable :devices="store.devices" :counts="store.counts" :scanning="store.scanning" />
    </div>

    <div class="full-row">
      <MaintenanceHistory />
    </div>

    <div v-if="confirmOpen" class="modal-backdrop" @click.self="closeRelaunch">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="relaunch-title">
        <h3 id="relaunch-title">ยืนยันการรีสตาร์ทบริการ</h3>
        <p class="muted">
          การรีสตาร์ทจะตัดการเชื่อมต่อชั่วคราว หน้าจอนี้จะพยายามเชื่อมต่อใหม่ให้อัตโนมัติ
          ภายใน 60 วินาที — พิมพ์คำว่า <span class="kbd">relaunch</span> เพื่อยืนยัน
        </p>
        <input
          v-model="confirmText"
          class="confirm-input"
          type="text"
          autocomplete="off"
          spellcheck="false"
          placeholder="relaunch"
          @keyup.enter="confirmRelaunch"
        />
        <div class="modal-actions">
          <button class="btn" :disabled="store.busy === 'relaunch'" @click="closeRelaunch">
            ยกเลิก
          </button>
          <button
            class="btn primary"
            :disabled="!confirmOk || store.busy === 'relaunch'"
            @click="confirmRelaunch"
          >
            {{ store.busy === 'relaunch' ? 'กำลังสั่งงาน…' : 'ยืนยันรีสตาร์ท' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.maintenance-page { display: flex; flex-direction: column; gap: 16px; }

.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.banner.error { border-color: var(--bad); color: var(--bad); }
.banner.notice { border-color: var(--info); color: var(--info); }

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.page-head h2 { margin: 0; font-size: 18px; display: flex; align-items: center; gap: 10px; }
.head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.full-row > :deep(.card) { width: 100%; }

.disk-list { display: flex; flex-direction: column; gap: 4px; margin: 4px 0 8px; }
.disk-chip { max-width: 100%; }

.action-list { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.as-button { margin-top: 8px; }

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

.confirm-input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
}
.confirm-input:focus {
  outline: none;
  border-color: var(--info);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
.modal-actions .btn { padding: 6px 14px; }

h3 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
</style>
