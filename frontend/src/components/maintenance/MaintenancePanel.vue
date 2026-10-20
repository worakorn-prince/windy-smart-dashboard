<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMaintenanceStore } from '@/stores/maintenance'

const store = useMaintenanceStore()

const targetOptions = [
  { value: 'user-temp', label: 'User Temp (%TEMP%)' },
  { value: 'windows-temp', label: 'Windows Temp (C:\\Windows\\Temp)' },
  { value: 'recycle-bin', label: 'Recycle Bin' },
] as const

const selectedTargets = ref<string[]>(['user-temp'])
const confirmingClean = ref(false)

const hasSelection = computed(() => selectedTargets.value.length > 0)
const cleaning = computed(() => store.busy === 'clean')

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
  confirmingClean.value = true
}

function cancelClean() {
  confirmingClean.value = false
}

async function confirmClean() {
  const targets = [...selectedTargets.value]
  const res = await store.runClean(targets)
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
        ยืนยันล้าง {{ selectedTargets.length }} เป้าหมาย? ไฟล์ในถังรีไซเคิลและโฟลเดอร์ชั่วคราวจะถูกลบถาวร
      </p>
      <ul class="target-list">
        <li v-for="value in selectedTargets" :key="value">
          {{ targetOptions.find((opt) => opt.value === value)?.label ?? value }}
        </li>
      </ul>
      <div class="action-list">
        <button class="danger" :disabled="cleaning" @click="confirmClean">
          {{ cleaning ? 'กำลังล้าง…' : 'ยืนยันการล้าง' }}
        </button>
        <button :disabled="cleaning" @click="cancelClean">ยกเลิก</button>
      </div>
    </div>
    <button v-else class="warn" :disabled="!!store.busy || !hasSelection" @click="requestClean">
      ล้างไฟล์ที่เลือก
    </button>
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
</style>
