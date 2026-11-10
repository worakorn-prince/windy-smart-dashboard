<script setup lang="ts">
import { computed } from 'vue'
import type { BatteryInfo } from '@/stores/metrics'

const props = defineProps<{ battery: BatteryInfo | null }>()

const percent = computed(() => {
  const p = props.battery?.percent
  return typeof p === 'number' && Number.isFinite(p) ? p : null
})

const barColor = computed(() => {
  const p = percent.value
  if (p == null) return 'var(--muted)'
  if (p >= 50) return 'var(--good)'
  if (p >= 20) return 'var(--warn)'
  return 'var(--bad)'
})

const status = computed(() => {
  if (!props.battery) return null
  return props.battery.charging ? '⚡ Charging' : 'On battery'
})

const timeRemaining = computed(() => {
  const t = props.battery?.time_remaining
  if (t == null || !Number.isFinite(t) || t < 0) return '—'
  const total = Math.round(t)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  return `${h}h ${m}m`
})

const health = computed(() => {
  const h = props.battery?.health_percent
  return h == null || !Number.isFinite(h) ? '—' : `${h.toFixed(1)}%`
})

const cycles = computed(() => {
  const c = props.battery?.cycle_count
  return c == null || !Number.isFinite(c) ? '—' : String(c)
})

const width = computed(() => {
  const p = percent.value
  if (p == null) return 0
  return Math.max(0, Math.min(100, p))
})
</script>

<template>
  <div class="card battery-card" data-testid="battery-card">
    <h3>Battery</h3>
    <div v-if="battery">
      <div class="hero">
        <span class="hero-value" data-testid="battery-percent" :style="{ color: barColor }">
          {{ percent == null ? '—' : `${percent.toFixed(0)}%` }}
        </span>
        <span class="hero-label" data-testid="battery-status">{{ status }}</span>
      </div>
      <div class="progress">
        <div :style="{ width: width + '%', background: barColor }"></div>
      </div>
      <div class="rows">
        <div class="row">
          <span class="label">Time remaining</span>
          <span class="value" data-testid="battery-time-remaining">{{ timeRemaining }}</span>
        </div>
        <div class="row">
          <span class="label">Health</span>
          <span class="value" data-testid="battery-health">{{ health }}</span>
        </div>
        <div class="row">
          <span class="label">Charge cycles</span>
          <span class="value" data-testid="battery-cycles">{{ cycles }}</span>
        </div>
      </div>
    </div>
    <p v-else class="muted" data-testid="battery-none">No battery detected</p>
  </div>
</template>

<style scoped>
.battery-card { min-width: 0; }
.hero {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 4px 0 10px;
}
.hero-value {
  font-size: 34px;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.hero-label { font-size: 12px; color: var(--muted); }
.progress { margin-bottom: 12px; }
.rows { display: flex; flex-direction: column; gap: 6px; }
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.row .label { color: var(--muted); }
.row .value { font-weight: 600; font-variant-numeric: tabular-nums; }
.muted { color: var(--muted); font-size: 12px; }
</style>
