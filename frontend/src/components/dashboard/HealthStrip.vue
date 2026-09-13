<script setup lang="ts">
import { computed } from 'vue'
import { useMetricsStore, severityOf, SEVERITY_COLORS, type SeverityLevel } from '@/stores/metrics'

const store = useMetricsStore()

const cpuValue = computed(() => store.cpu?.overall ?? 0)
const ramValue = computed(() => store.ram?.percent ?? 0)

const tempValue = computed(() => {
  const candidates: number[] = []
  const cpuTemp = store.cpu?.temperature_celsius
  if (cpuTemp?.primary !== null && cpuTemp?.primary !== undefined) candidates.push(cpuTemp.primary)
  if (cpuTemp?.max !== null && cpuTemp?.max !== undefined) candidates.push(cpuTemp.max)
  for (const g of store.gpu?.gpus ?? []) {
    if (g.temperature_celsius !== null && g.temperature_celsius !== undefined) candidates.push(g.temperature_celsius)
  }
  const ramTemps = store.ram?.temperature_celsius?.temps ?? []
  for (const t of ramTemps) {
    if (t.value !== null && t.value !== undefined) candidates.push(t.value)
  }
  if (candidates.length === 0) return 0
  return Math.max(...candidates)
})

const cpuSev = computed(() => severityOf('cpu', cpuValue.value))
const ramSev = computed(() => severityOf('ram', ramValue.value))
const tempSev = computed(() => severityOf('temp', tempValue.value))

const rank: Record<SeverityLevel, number> = { ok: 0, warn: 1, crit: 2 }

const overall = computed<SeverityLevel>(() => {
  let worst: SeverityLevel = 'ok'
  for (const s of [cpuSev.value, ramSev.value, tempSev.value]) {
    if (rank[s] > rank[worst]) worst = s
  }
  return worst
})

const pendingAlerts = computed(() => store.alerts.length)

const statusText = computed(() => {
  if (overall.value === 'crit') return 'วิกฤต'
  if (overall.value === 'warn') return 'ควรเฝ้าระวัง'
  return 'ระบบปกติ'
})

const dotColor = computed(() => SEVERITY_COLORS[overall.value])
</script>

<template>
  <section
    class="health-strip"
    :class="`sev-${overall}`"
    data-testid="health-strip"
    :data-severity="overall"
  >
    <span
      class="dot"
      data-testid="health-dot"
      :data-severity="overall"
      :style="{ background: dotColor }"
    />
    <strong class="status" data-testid="health-status">{{ statusText }}</strong>
    <span class="metrics" data-testid="health-metrics">
      CPU {{ Math.round(cpuValue) }}% · RAM {{ Math.round(ramValue) }}% · Temp {{ Math.round(tempValue) }}°C
    </span>
    <span class="alerts" data-testid="health-alerts">
      เตือนค้าง {{ pendingAlerts }} รายการ
    </span>
  </section>
</template>

<style scoped>
.health-strip {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 16px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--panel);
  border-left-width: 4px;
}
.health-strip.sev-ok { border-left-color: var(--good); }
.health-strip.sev-warn { border-left-color: var(--warn); }
.health-strip.sev-crit { border-left-color: var(--bad); }
.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status { font-size: 14px; }
.metrics { color: var(--muted); font-variant-numeric: tabular-nums; }
.alerts {
  margin-left: auto;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
</style>
