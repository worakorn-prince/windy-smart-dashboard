<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useMetricsStore } from '@/stores/metrics'
import StatTile from '@/components/dashboard/StatTile.vue'

type Accent = 'cyan' | 'violet' | 'lime' | 'amber'
type DeltaTone = 'good' | 'bad' | 'flat'

interface TileSpec {
  label: string
  value: string
  unit?: string
  accent: Accent
  icon: string
  delta?: string | null
  deltaTone?: DeltaTone
  caption?: string
  subtitle?: string
  spark?: number[]
}

interface DeltaInfo {
  text: string
  tone: DeltaTone
}

const store = useMetricsStore()

const MAX_POINTS = 60
const CLOCK_INTERVAL_MS = 30_000

const gpuHistory = ref<number[]>([])
const powerHistory = ref<number[]>([])
const firstSampleAt = ref<number | null>(null)
const now = ref(Date.now())

let clockTimer: number | undefined

onMounted(() => {
  clockTimer = window.setInterval(() => {
    now.value = Date.now()
  }, CLOCK_INTERVAL_MS)
})

onUnmounted(() => {
  if (clockTimer !== undefined) window.clearInterval(clockTimer)
})

function pushSample(history: number[], value: number): void {
  history.push(value)
  if (history.length > MAX_POINTS) history.shift()
}

const cpuUsage = computed<number | null>(() => {
  const v = store.cpu?.overall
  return typeof v === 'number' && Number.isFinite(v) ? v : null
})

const gpuUsage = computed<number | null>(() => {
  const values = (store.gpu?.gpus ?? [])
    .map((g) => g.gpu_usage_percent)
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (!values.length) return null
  return values.reduce((sum, v) => sum + v, 0) / values.length
})

const ramUsed = computed<number | null>(() => {
  const v = store.ram?.used
  return typeof v === 'number' && Number.isFinite(v) ? v : null
})

const ramPercent = computed<number | null>(() => {
  const v = store.ram?.percent
  return typeof v === 'number' && Number.isFinite(v) ? v : null
})

const ramTotal = computed<number | null>(() => {
  const v = store.ram?.total
  return typeof v === 'number' && Number.isFinite(v) ? v : null
})

const totalPower = computed<number | null>(() => {
  const parts: number[] = []
  const cpuPower = store.cpu?.power_watts
  if (typeof cpuPower === 'number' && Number.isFinite(cpuPower)) parts.push(cpuPower)
  for (const gpu of store.gpu?.gpus ?? []) {
    const p = gpu.power_draw_watts
    if (typeof p === 'number' && Number.isFinite(p)) parts.push(p)
  }
  if (!parts.length) return null
  return parts.reduce((sum, v) => sum + v, 0)
})

watch(gpuUsage, (v) => {
  if (v != null) pushSample(gpuHistory.value, v)
})

watch(totalPower, (v) => {
  if (v != null) pushSample(powerHistory.value, v)
})

watch(
  [() => store.cpuHistory.length, () => store.ramHistory.length],
  () => {
    if (firstSampleAt.value == null && (store.cpuHistory.length || store.ramHistory.length)) {
      firstSampleAt.value = Date.now()
    }
  },
  { immediate: true },
)

const caption = computed(() => {
  if (firstSampleAt.value == null) return 'กำลังเก็บข้อมูล…'
  const minutes = Math.max(1, Math.floor((now.value - firstSampleAt.value) / 60_000))
  if (minutes < 60) return `เชียร์ ${minutes} นาทีที่แล้ว`
  const hours = Math.floor(minutes / 60)
  return `เชียร์ ${hours} ชั่วโมงที่แล้ว`
})

function peakDelta(
  history: number[],
  current: number | null,
  format: (gap: number) => string,
  tone: (gap: number) => DeltaTone,
): DeltaInfo | null {
  if (current == null || history.length < 2) return null
  const peak = Math.max(...history)
  const gap = peak - current
  if (gap < 0.5) return { text: format(0), tone: tone(0) }
  return { text: format(gap), tone: tone(gap) }
}

const cpuDelta = computed<DeltaInfo | null>(() =>
  peakDelta(
    store.cpuHistory,
    cpuUsage.value,
    (gap) => `+${Math.round(gap)} จุดเดิมสูงสุด`,
    (gap) => (gap > 0 ? 'good' : 'flat'),
  ),
)

const gpuDelta = computed<DeltaInfo | null>(() =>
  peakDelta(
    gpuHistory.value,
    gpuUsage.value,
    (gap) => `+${Math.round(gap)} จุดเดิมสูงสุด`,
    (gap) => (gap > 0 ? 'good' : 'flat'),
  ),
)

const ramDelta = computed<DeltaInfo | null>(() =>
  peakDelta(
    store.ramHistory,
    ramPercent.value,
    (gap) => `+${Math.round(gap)} จุดเดิมสูงสุด`,
    (gap) => (gap > 0 ? 'good' : 'flat'),
  ),
)

const powerDelta = computed<DeltaInfo | null>(() =>
  peakDelta(
    powerHistory.value,
    totalPower.value,
    (gap) => `+${Math.round(gap)} W`,
    () => 'flat',
  ),
)

const tiles = computed<TileSpec[]>(() => {
  const cap = caption.value

  const cpuTile: TileSpec = {
    label: 'CPU',
    value: cpuUsage.value == null ? '—' : cpuUsage.value.toFixed(0),
    accent: 'cyan',
    icon: '◉',
    delta: cpuDelta.value?.text ?? null,
    deltaTone: cpuDelta.value?.tone ?? 'flat',
    caption: cap,
    subtitle: store.cpu?.info?.Name ?? '',
    spark: cpuUsage.value == null ? [] : store.cpuHistory,
  }
  if (cpuUsage.value != null) cpuTile.unit = '%'

  const gpuTile: TileSpec = {
    label: 'GPU',
    value: gpuUsage.value == null ? '—' : gpuUsage.value.toFixed(0),
    accent: 'violet',
    icon: '◈',
    delta: gpuDelta.value?.text ?? null,
    deltaTone: gpuDelta.value?.tone ?? 'flat',
    caption: cap,
    subtitle: store.gpu?.gpus?.[0]?.name ?? '',
    spark: gpuUsage.value == null ? [] : gpuHistory.value,
  }
  if (gpuUsage.value != null) gpuTile.unit = '%'

  const ramTile: TileSpec = {
    label: 'RAM',
    value: ramUsed.value == null ? '—' : ramUsed.value.toFixed(1),
    accent: 'lime',
    icon: '▦',
    delta: ramDelta.value?.text ?? null,
    deltaTone: ramDelta.value?.tone ?? 'flat',
    caption: cap,
    subtitle:
      ramTotal.value != null && ramPercent.value != null
        ? `จากทั้งหมด ${ramTotal.value.toFixed(0)} GB · ใช้ ${Math.round(ramPercent.value)}%`
        : '',
    spark: ramUsed.value == null ? [] : store.ramHistory,
  }
  if (ramUsed.value != null) ramTile.unit = 'GB'

  const powerTile: TileSpec = {
    label: 'POWER',
    value: totalPower.value == null ? '—' : totalPower.value.toFixed(0),
    accent: 'amber',
    icon: '⚡',
    delta: powerDelta.value?.text ?? null,
    deltaTone: powerDelta.value?.tone ?? 'flat',
    caption: cap,
    subtitle: totalPower.value == null ? '' : 'กำลังใช้ไฟของระบบ',
    spark: totalPower.value == null ? [] : powerHistory.value,
  }
  if (totalPower.value != null) powerTile.unit = 'W'

  return [cpuTile, gpuTile, ramTile, powerTile]
})
</script>

<template>
  <section class="stat-row" data-testid="stat-row">
    <StatTile v-for="tile in tiles" :key="tile.label" v-bind="tile" />
  </section>
</template>

<style scoped>
.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

@media (max-width: 1100px) {
  .stat-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .stat-row {
    grid-template-columns: 1fr;
  }
}
</style>
