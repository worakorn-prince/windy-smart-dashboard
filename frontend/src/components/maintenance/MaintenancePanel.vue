<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMaintenanceStore } from '@/stores/maintenance'
import { formatBytes, formatDuration } from '@/utils/format'

const store = useMaintenanceStore()

const targetOptions = [
  { value: 'user-temp', label: 'User Temp (%TEMP%)' },
  { value: 'windows-temp', label: 'Windows Temp (C:\\Windows\\Temp)' },
  { value: 'recycle-bin', label: 'Recycle Bin' },
] as const

const selectedTargets = ref<string[]>(['user-temp'])
const confirmingClean = ref(false)
const confirmMode = ref<'selected' | 'all'>('selected')

const hasSelection = computed(() => selectedTargets.value.length > 0)
const cleaning = computed(() => store.busy === 'clean')

const summaryItems = computed(() => store.cleanSummary?.categories ?? [])
const allTargets = computed(() =>
  summaryItems.value
    .map((item) => item.target)
    .filter((value): value is string => typeof value === 'string' && value.length > 0),
)
const confirmTargets = computed(() =>
  confirmMode.value === 'all' ? [...allTargets.value] : [...selectedTargets.value],
)

function targetLabel(value?: string): string {
  if (!value) return '—'
  return targetOptions.find((opt) => opt.value === value)?.label ?? value
}

onMounted(() => {
  store.loadCleanSummary()
})

function formatDate(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const raw = String(value)
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

function toggleTarget(value: string) {
  selectedTargets.value = selectedTargets.value.includes(value)
    ? selectedTargets.value.filter((v) => v !== value)
    : [...selectedTargets.value, value]
}

async function refresh() {
  await store.loadScan(false)
}

async function rescan() {
  await store.loadScan(true)
}

async function doAction(action: 'wu-scan' | 'pnputil-scan') {
  const res = await store.runAction(action)
  if (res) await store.loadHistory()
}

function requestClean() {
  if (!hasSelection.value) {
    store.error = 'กรุณาเลือกเป้าหมายที่ต้องการล้างอย่างน้อยหนึ่งรายการ'
    return
  }
  confirmMode.value = 'selected'
  confirmingClean.value = true
}

function requestCleanAll() {
  if (!allTargets.value.length) {
    store.error = 'ยังไม่มีรายการเป้าหมายจากสรุปขนาดไฟล์ กรุณารีเฟรชก่อนล้างทั้งหมด'
    return
  }
  confirmMode.value = 'all'
  confirmingClean.value = true
}

function cancelClean() {
  confirmingClean.value = false
}

async function confirmClean() {
  const targets = confirmTargets.value
  if (!targets.length) {
    store.error = 'ไม่มีเป้าหมายให้ล้าง กรุณารีเฟรชข้อมูลก่อน'
    confirmingClean.value = false
    return
  }
  const res = await store.runClean(targets, true)
  confirmingClean.value = false
  if (res) await store.loadHistory()
}
</script>

<template>
  <div class="card maintenance-panel">
    <h3>
      เครื่องมือบำรุงรักษา
      <span v-if="store.scannedAt" class="muted small meta">สแกนล่าสุด: {{ formatDate(store.scannedAt) }}</span>
      <span v-if="store.cached" class="badge info">cached</span>
    </h3>

    <div class="toolbar">
      <button :disabled="store.scanning || !!store.busy" @click="refresh">
        {{ store.scanning ? 'กำลังสแกน…' : 'รีเฟรช' }}
      </button>
      <button class="primary" :disabled="store.scanning || !!store.busy" @click="rescan">
        {{ store.scanning ? 'กำลังสแกน…' : 'สแกนใหม่' }}
      </button>
    </div>

    <h4>Actions</h4>
    <p class="muted small">เรียกเครื่องมือตรวจสอบของ Windows ผ่านเซิร์ฟเวอร์</p>
    <div class="action-list">
      <button :disabled="!!store.busy" @click="doAction('wu-scan')">
        {{ store.busy === 'wu-scan' ? 'กำลังทำงาน…' : 'Windows Update scan (wu-scan)' }}
      </button>
      <button :disabled="!!store.busy" @click="doAction('pnputil-scan')">
        {{ store.busy === 'pnputil-scan' ? 'กำลังทำงาน…' : 'Driver scan (pnputil-scan)' }}
      </button>
    </div>
    <p v-if="store.busy" class="muted small">busy: {{ store.busy }}</p>

    <section class="clean-summary" aria-label="ขนาดขยะก่อนล้าง">
      <div class="summary-head">
        <h4>ขนาดขยะก่อนล้าง</h4>
        <button :disabled="store.summaryLoading" @click="store.loadCleanSummary()">
          {{ store.summaryLoading ? 'กำลังโหลด…' : 'รีเฟรชขนาด' }}
        </button>
      </div>

      <p v-if="store.summaryLoading" class="muted small" role="status">กำลังโหลดขนาดไฟล์…</p>
      <p v-else-if="store.summaryError" class="muted small summary-error" role="status">
        {{ store.summaryError }}
      </p>

      <table v-if="!store.summaryLoading && summaryItems.length" class="summary-table">
        <thead>
          <tr>
            <th scope="col">เป้าหมาย</th>
            <th scope="col">พาธ</th>
            <th scope="col" class="num">ขนาด</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in summaryItems" :key="item.target || index">
            <td>{{ targetLabel(item.target) }}</td>
            <td class="path" :title="item.path || ''">{{ item.path || '—' }}</td>
            <td class="num">{{ formatBytes(item.bytes) }}</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" colspan="2">รวมทั้งหมด</th>
            <td class="num">{{ formatBytes(store.cleanSummary?.totalBytes) }}</td>
          </tr>
          <tr>
            <th scope="row" colspan="2">ใช้เวลาสแกน</th>
            <td class="num">{{ formatDuration(store.cleanSummary?.durationMs) }}</td>
          </tr>
        </tfoot>
      </table>
      <p v-else-if="!store.summaryLoading && !store.summaryError" class="muted small">
        ยังไม่มีข้อมูลขนาดไฟล์
      </p>
    </section>

    <h4>ล้างไฟล์ชั่วคราว</h4>
    <label v-for="opt in targetOptions" :key="opt.value" class="check-row">
      <input
        type="checkbox"
        :value="opt.value"
        :checked="selectedTargets.includes(opt.value)"
        :disabled="cleaning"
        @change="toggleTarget(opt.value)"
      />
      <span>{{ opt.label }}</span>
    </label>

    <div
      v-if="confirmingClean"
      class="confirm-box"
      role="group"
      aria-label="ยืนยันการล้างไฟล์"
      aria-live="polite"
    >
      <p class="muted small">
        ยืนยันล้าง {{ confirmTargets.length }} เป้าหมาย? ไฟล์ในถังรีไซเคิลและโฟลเดอร์ชั่วคราวจะถูกลบถาวร
      </p>
      <ul class="target-list">
        <li v-for="value in confirmTargets" :key="value">{{ targetLabel(value) }}</li>
      </ul>
      <div class="action-list">
        <button class="danger" :disabled="cleaning" @click="confirmClean">
          {{ cleaning ? 'กำลังล้าง…' : 'ยืนยันการล้าง' }}
        </button>
        <button :disabled="cleaning" @click="cancelClean">ยกเลิก</button>
      </div>
    </div>
    <div v-else class="action-list">
      <button class="warn" :disabled="!!store.busy || !hasSelection" @click="requestClean">
        ล้างไฟล์ที่เลือก
      </button>
      <button
        class="danger"
        :disabled="!!store.busy || !allTargets.length || store.summaryLoading"
        aria-label="ล้างไฟล์ทั้งหมดตามรายการในสรุปขนาดขยะ"
        @click="requestCleanAll"
      >
        ล้างทั้งหมด
      </button>
    </div>

    <section v-if="store.lastClean" class="last-clean" role="status" aria-label="ผลการล้างล่าสุด">
      <h4>ล้างล่าสุด</h4>
      <p class="muted small">
        ปลดปล่อยพื้นที่ {{ formatBytes(store.lastClean.bytesFreed) }} · ใช้เวลา
        {{ formatDuration(store.lastClean.durationMs) }}
      </p>
      <p class="muted small">เป้าหมาย: {{ (store.lastClean.targets || []).join(', ') || '—' }}</p>
    </section>
  </div>
</template>

<style scoped>
h3 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
h4 { margin: 14px 0 6px; font-size: 12px; }
.meta { font-weight: 500; text-transform: none; letter-spacing: 0; }

.toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.action-list { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }

.check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
}
.check-row input { accent-color: var(--accent); }

.confirm-box {
  margin-top: 10px;
  padding: 10px;
  border: 1px solid var(--warn);
  border-radius: 8px;
  background: rgba(255, 215, 95, 0.08);
}
.confirm-box p { margin: 0; }
.target-list { margin: 6px 0 0; padding-left: 18px; font-size: 11.5px; }

.clean-summary { margin-top: 12px; }
.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.summary-head h4 { margin: 0; }

.summary-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 8px;
  font-size: 11.5px;
}
.summary-table th,
.summary-table td {
  padding: 5px 6px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
.summary-table thead th {
  font-size: 11px;
  color: var(--muted);
  font-weight: 600;
}
.summary-table td.path {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--muted);
}
.summary-table .num { text-align: right; white-space: nowrap; }
.summary-table tfoot th,
.summary-table tfoot td {
  font-weight: 600;
  border-bottom: none;
}
.summary-error { color: var(--warn); }

.last-clean {
  margin-top: 12px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
}
.last-clean h4 { margin-top: 0; }
.last-clean p { margin: 2px 0; }
</style>
