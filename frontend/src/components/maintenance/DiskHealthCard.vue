<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

interface DiskInfo {
  mount: string
  total_gb: number
  used_gb: number
  used_pct: number
}

interface SmartDisk {
  FriendlyName?: string
  MediaType?: string
  HealthStatus?: string
  OperationalStatus?: string
}

interface SmartInfo {
  available: boolean
  disks?: SmartDisk[]
  error?: string
}

interface Prediction {
  mount: string
  days_to_full: number | null
  trend_gb_per_day: number | null
  samples: number
}

interface DiskHealthPayload {
  disks: DiskInfo[]
  smart: SmartInfo
  predictions: Prediction[]
  sampled_at: string | null
}

const data = ref<DiskHealthPayload | null>(null)
const loading = ref(false)
const error = ref('')

const smartDisks = computed(() => data.value?.smart.disks ?? [])

const predictionsByMount = computed(() => {
  const map = new Map<string, Prediction>()
  for (const prediction of data.value?.predictions ?? []) {
    map.set(prediction.mount, prediction)
  }
  return map
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/health/disk', { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const body = (await response.json()) as DiskHealthPayload
    data.value = {
      disks: Array.isArray(body.disks) ? body.disks : [],
      smart: body.smart ?? { available: false },
      predictions: Array.isArray(body.predictions) ? body.predictions : [],
      sampled_at: body.sampled_at ?? null,
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'โหลดข้อมูลสุขภาพดิสก์ไม่สำเร็จ'
  } finally {
    loading.value = false
  }
}

function formatGb(value: number): string {
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '—'
  return `${amount.toLocaleString('th-TH', { maximumFractionDigits: 1 })} GB`
}

function percentOf(disk: DiskInfo): number {
  const raw = Number(disk.used_pct)
  if (Number.isFinite(raw)) return Math.min(Math.max(raw, 0), 100)
  const total = Number(disk.total_gb)
  const used = Number(disk.used_gb)
  if (Number.isFinite(total) && total > 0 && Number.isFinite(used)) {
    return Math.min(Math.max((used / total) * 100, 0), 100)
  }
  return 0
}

function barClass(disk: DiskInfo): string {
  const percent = percentOf(disk)
  if (percent >= 90) return 'bad'
  if (percent >= 75) return 'warn'
  return 'ok'
}

function predictionText(prediction: Prediction | undefined): string {
  if (!prediction) return 'ข้อมูลไม่พอ'
  if (prediction.days_to_full !== null && prediction.days_to_full !== undefined) {
    return `เต็มใน ~${formatDays(prediction.days_to_full)} วัน`
  }
  if (prediction.samples < 3) return 'ข้อมูลไม่พอ'
  if (prediction.trend_gb_per_day !== null && prediction.trend_gb_per_day <= 0) {
    return 'ไม่มีความเสี่ยง'
  }
  return 'ข้อมูลไม่พอ'
}

function formatDays(days: number): string {
  if (days < 1) return 'น้อยกว่า 1'
  return Math.round(days).toLocaleString('th-TH')
}

function isRisk(prediction: Prediction | undefined): boolean {
  return prediction?.days_to_full !== null
    && prediction?.days_to_full !== undefined
    && prediction.days_to_full <= 30
}

function smartBadgeClass(status: string | undefined): string {
  const normalized = (status || '').toLowerCase()
  if (normalized === 'healthy') return 'good'
  if (normalized === 'warning' || normalized === 'caution') return 'warn'
  return 'muted'
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="card disk-health">
    <h3>
      สุขภาพดิสก์ (SMART)
      <button class="btn tiny" :disabled="loading" @click="load">
        {{ loading ? 'กำลังโหลด…' : 'รีเฟรช' }}
      </button>
    </h3>

    <p v-if="loading && !data" class="muted" role="status">กำลังโหลดข้อมูลดิสก์…</p>

    <template v-else-if="data">
      <p v-if="error" class="error-text" role="alert">{{ error }}</p>

      <p v-if="!data.disks.length" class="muted small">ไม่พบดิสก์แบบ fixed drive</p>
      <ul v-else class="disk-list">
        <li v-for="disk in data.disks" :key="disk.mount" class="disk-row">
          <div class="disk-head">
            <span class="mount">{{ disk.mount }}</span>
            <span class="muted small">
              {{ formatGb(disk.used_gb) }} / {{ formatGb(disk.total_gb) }}
              · {{ percentOf(disk).toFixed(1) }}%
            </span>
          </div>
          <div
            class="bar"
            role="img"
            :aria-label="`${disk.mount} ใช้พื้นที่ ${percentOf(disk).toFixed(1)}%`"
          >
            <span
              class="bar-fill"
              :class="barClass(disk)"
              :style="{ width: `${percentOf(disk)}%` }"
            />
          </div>
          <p
            class="prediction"
            :class="{ risk: isRisk(predictionsByMount.get(disk.mount)) }"
          >
            {{ predictionText(predictionsByMount.get(disk.mount)) }}
            <span
              v-if="predictionsByMount.get(disk.mount)"
              class="muted small"
            >
              ({{ predictionsByMount.get(disk.mount)?.samples ?? 0 }} samples)
            </span>
          </p>
        </li>
      </ul>

      <h4>สถานะ SMART</h4>
      <div v-if="data.smart.available && smartDisks.length" class="smart-list">
        <div v-for="(smart, index) in smartDisks" :key="index" class="smart-row">
          <span class="smart-name">{{ smart.FriendlyName || `Disk ${index + 1}` }}</span>
          <span class="muted small">
            {{ smart.MediaType || 'ไม่ทราบชนิด' }}
            <template v-if="smart.OperationalStatus"> · {{ smart.OperationalStatus }}</template>
          </span>
          <span class="badge smart-badge" :class="smartBadgeClass(smart.HealthStatus)">
            {{ smart.HealthStatus || 'Unknown' }}
          </span>
        </div>
      </div>
      <p v-else class="muted small smart-unavailable">
        <span class="badge smart-badge muted">Unknown</span>
        {{ data.smart.error || 'ไม่สามารถอ่านสถานะ SMART ได้' }}
      </p>

      <p class="muted small sampled-at">เก็บข้อมูลเมื่อ {{ formatDate(data.sampled_at) }}</p>
    </template>

    <div v-else-if="error" class="error-box" role="alert">
      <span>{{ error }}</span>
      <button class="btn tiny" @click="load">ลองใหม่</button>
    </div>

    <p v-else class="muted">ยังไม่มีข้อมูลดิสก์</p>
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
h4 { margin: 14px 0 6px; font-size: 12px; }

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

.disk-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.disk-row { display: flex; flex-direction: column; gap: 5px; }
.disk-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.mount { font-weight: 600; font-size: 12.5px; }

.bar {
  height: 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-2);
  overflow: hidden;
}
.bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.25s ease;
}
.bar-fill.ok { background: var(--good); }
.bar-fill.warn { background: var(--warn); }
.bar-fill.bad { background: var(--bad); }

.prediction { margin: 0; font-size: 11.5px; color: var(--muted); }
.prediction.risk { color: var(--bad); font-weight: 600; }

.smart-list { display: flex; flex-direction: column; gap: 6px; }
.smart-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
}
.smart-name { font-size: 11.5px; font-weight: 600; }
.smart-badge { margin-left: auto; }
.smart-badge.good { background: var(--good); color: #0a2a14; }
.smart-badge.warn { background: var(--warn); color: #2a1f0a; }
.smart-badge.muted { background: var(--border); color: var(--muted); }
.smart-unavailable { margin: 0; }
.sampled-at { margin: 10px 0 0; }

.error-text {
  margin: 0 0 10px;
  padding: 6px 9px;
  border: 1px solid var(--bad);
  border-radius: 6px;
  color: var(--bad);
  font-size: 11.5px;
}
.error-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--bad);
  border-radius: 6px;
  color: var(--bad);
}
</style>
