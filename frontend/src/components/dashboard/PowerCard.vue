<script setup lang="ts">
import { computed, ref } from 'vue'
import { useMetricsStore } from '@/stores/metrics'

const collapsed = ref(false)
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

const otherW = computed(() => {
  if (totalW.value === null) return 0
  const known = (cpuW.value ?? 0) + (gpuW.value ?? 0)
  const rest = totalW.value - known
  return rest > 0.05 ? Math.round(rest * 10) / 10 : 0
})

function pctOf(value: number | null): number {
  if (value === null || !totalW.value || totalW.value <= 0) return 0
  return Math.max(0, Math.min(100, (value / totalW.value) * 100))
}

const cpuPct = computed(() => pctOf(cpuW.value))
const gpuPct = computed(() => pctOf(gpuW.value))
const otherPct = computed(() => pctOf(otherW.value || null))

const gpuList = computed(() =>
  (store.gpu?.gpus ?? [])
    .map((g) => ({ name: g.name, w: g.power_draw_watts ?? null }))
    .filter((g) => g.w != null),
)

const cpuText = computed(() => (cpuW.value === null ? '—' : `${Math.round(cpuW.value)} W`))
const gpuText = computed(() => (gpuW.value === null ? '—' : `${Math.round(gpuW.value)} W`))
const otherText = computed(() => `${Math.round(otherW.value)} W`)

const fmt = (v: number | null) => (v == null ? '—' : `${v.toFixed(1)} W`)
</script>

<template>
  <div class="card power-card">
    <h3 class="card-title">
      <span>พลังงานของระบบ</span>
      <span v-if="totalW !== null" class="total-watts" data-testid="power-total">{{ totalW.toFixed(0) }} W</span>
      <button
        type="button"
        class="card-toggle"
        data-testid="card-toggle"
        :aria-expanded="!collapsed"
        :aria-label="collapsed ? 'Expand power details' : 'Collapse power details'"
        @click="collapsed = !collapsed"
      >
        {{ collapsed ? '+' : '−' }}
      </button>
    </h3>

    <div v-show="!collapsed">
      <template v-if="totalW !== null">
        <div class="power-bar" role="img" aria-label="การกระจายกำลังไฟของระบบ">
          <span class="seg cpu" :style="{ width: cpuPct + '%' }"></span>
          <span class="seg gpu" :style="{ width: gpuPct + '%' }"></span>
          <span class="seg other" :style="{ width: otherPct + '%' }"></span>
        </div>

        <div class="rows">
          <div v-if="cpuW !== null" class="row">
            <span class="label">CPU</span>
            <span class="value">{{ cpuText }}</span>
          </div>
          <div v-if="gpuW !== null" class="row">
            <span class="label">GPU</span>
            <span class="value">{{ gpuText }}</span>
          </div>
          <div v-if="otherW > 0" class="row">
            <span class="label">อื่น ๆ</span>
            <span class="value">{{ otherText }}</span>
          </div>
          <div v-for="g in gpuList" :key="g.name" class="row sub">
            <span class="label">{{ g.name }}</span>
            <span class="value">{{ fmt(g.w) }}</span>
          </div>
        </div>
      </template>
      <p v-else class="muted">No power data — run the dashboard as Administrator.</p>
    </div>
  </div>
</template>

<style scoped>
.power-card { min-width: 0; }
.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  text-transform: none;
  letter-spacing: normal;
  overflow: visible;
  white-space: normal;
}
.card-title > span:first-child { flex: 1; min-width: 0; }
.total-watts {
  font-family: var(--font-mono);
  font-size: 30px;
  font-weight: 800;
  line-height: 1;
  color: var(--accent-4);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.card-toggle {
  width: 24px;
  height: 24px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-ctl);
  color: var(--muted);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  flex: none;
}
.card-toggle:hover {
  color: var(--text);
  border-color: var(--border-strong);
  background: var(--panel-2);
}
.power-bar {
  height: 8px;
  display: flex;
  border-radius: 999px;
  overflow: hidden;
  background: var(--panel-2);
  margin: 2px 0 14px;
}
.power-bar .seg {
  height: 100%;
  transition: width 0.4s ease;
}
.power-bar .seg.cpu { background: var(--accent); }
.power-bar .seg.gpu { background: var(--accent-3); }
.power-bar .seg.other { background: var(--accent-4); }
.rows { display: flex; flex-direction: column; gap: 6px; }
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
.row .label { color: var(--muted); }
.row .value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.row.sub { padding-left: 10px; font-size: 12px; }
.row.sub .label {
  max-width: 70%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.muted { color: var(--muted); font-size: 12px; }
</style>
