<script setup lang="ts">
import { computed } from 'vue'
import { useMetricsStore } from '@/stores/metrics'

const store = useMetricsStore()

const cpuW = computed(() => store.cpu?.power_watts ?? null)
const gpuW = computed(() => {
  const gpus = store.gpu?.gpus ?? []
  const vals = gpus.map((g) => g.power_draw_watts).filter((v): v is number => v != null)
  if (!vals.length) return null
  return Math.round(vals.reduce((a, b) => a + b, 0) * 10) / 10
})
const totalW = computed(() => {
  const parts = [cpuW.value, gpuW.value].filter((v): v is number => v != null)
  if (!parts.length) return null
  return Math.round(parts.reduce((a, b) => a + b, 0) * 10) / 10
})

const gpuList = computed(() =>
  (store.gpu?.gpus ?? [])
    .map((g) => ({ name: g.name, w: g.power_draw_watts ?? null }))
    .filter((g) => g.w != null),
)

const fmt = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)} W`)
</script>

<template>
  <div class="card power-card">
    <h3>Power Usage</h3>

    <div v-if="totalW != null" class="total">
      <span class="total-value">{{ totalW.toFixed(1) }}</span>
      <span class="total-unit">W now</span>
    </div>
    <p v-else class="muted">No power data — run the dashboard as Administrator.</p>

    <div class="rows">
      <div class="row" v-if="cpuW != null">
        <span class="label">CPU</span>
        <span class="value">{{ fmt(cpuW) }}</span>
      </div>
      <div class="row" v-if="gpuW != null">
        <span class="label">GPU</span>
        <span class="value">{{ fmt(gpuW) }}</span>
      </div>
      <div class="row sub" v-for="g in gpuList" :key="g.name">
        <span class="label">{{ g.name }}</span>
        <span class="value">{{ fmt(g.w) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.power-card { min-width: 0; }
.total {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 4px 0 14px;
}
.total-value {
  font-size: 34px;
  font-weight: 800;
  line-height: 1;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.total-unit { font-size: 12px; color: var(--muted); }
.rows { display: flex; flex-direction: column; gap: 6px; }
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.row .label { color: var(--muted); }
.row .value { font-weight: 600; font-variant-numeric: tabular-nums; }
.row.sub { padding-left: 10px; font-size: 12px; }
.row.sub .label {
  max-width: 70%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.muted { color: var(--muted); font-size: 12px; }
</style>
