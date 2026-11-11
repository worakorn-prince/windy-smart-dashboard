<script setup lang="ts">
import { computed } from 'vue'
import { useMetricsStore, type ProcessInfo } from '@/stores/metrics'

defineProps<{ processes: ProcessInfo[]; selectedPid?: number | null }>()
const emit = defineEmits<{ select: [pid: number] }>()

const store = useMetricsStore()

const totalRamGb = computed<number | null>(() => {
  const total = store.ram?.total
  if (typeof total !== 'number' || !Number.isFinite(total) || total <= 0) return null
  return total
})

function truncateName(name: string, max = 28): string {
  if (!name) return ''
  return name.length > max ? name.slice(0, max - 1) + '…' : name
}

function cpuLevel(cpu: number): 'is-bad' | 'is-warn' | 'is-ok' {
  if (cpu >= 50) return 'is-bad'
  if (cpu >= 25) return 'is-warn'
  return 'is-ok'
}

function ramText(p: ProcessInfo): string {
  const percent = p.ram_percent ?? 0
  if (totalRamGb.value !== null) {
    return `${((percent / 100) * totalRamGb.value).toFixed(1)} GB`
  }
  return `${percent.toFixed(1)}%`
}
</script>

<template>
  <div class="card processes-card">
    <h3 class="card-title">
      <span>โปรเซสส์ที่กำลังทำงาน</span>
      <span class="count-badge" data-testid="process-count">{{ processes.length }}</span>
    </h3>

    <table v-if="processes.length" class="proc-table">
      <thead>
        <tr>
          <th class="col-name">ชื่อโปรเซส</th>
          <th class="col-cpu">CPU %</th>
          <th class="col-ram">RAM</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="p in processes"
          :key="p.pid"
          class="clickable"
          :class="{ selected: p.pid === selectedPid }"
          tabindex="0"
          @click="emit('select', p.pid)"
          @keydown.enter="emit('select', p.pid)"
          @keydown.space.prevent="emit('select', p.pid)"
        >
          <td class="col-name">
            <span class="proc-name" :data-fulltext="p.name" v-auto-tip>{{ truncateName(p.name) }}</span>
          </td>
          <td class="col-cpu">
            <span class="cpu-value" :class="cpuLevel(p.cpu)">{{ p.cpu.toFixed(1) }}%</span>
          </td>
          <td class="col-ram">{{ ramText(p) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Waiting for data…</p>
  </div>
</template>

<style scoped>
.processes-card { display: flex; flex-direction: column; }
.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  text-transform: none;
  letter-spacing: normal;
  overflow: visible;
  white-space: normal;
}
.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  padding: 1px 8px;
  border-radius: var(--radius-pill);
  background: var(--panel-2);
  border: 1px solid var(--border);
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  line-height: 1.6;
}
.proc-table th.col-name { width: 46%; }
.proc-table th.col-cpu { width: 22%; }
.proc-table th.col-ram { width: 32%; text-align: right; }
.proc-table td.col-ram {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text-dim);
}
.proc-name {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-dim);
}
.cpu-value {
  font-family: var(--font-mono);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.cpu-value.is-ok { color: var(--accent); }
.cpu-value.is-warn { color: var(--warn); }
.cpu-value.is-bad { color: var(--bad); }
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: var(--accent-soft); }
tr.clickable:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
tr.selected {
  background: var(--accent-soft);
  box-shadow: inset 2px 0 0 var(--accent);
}
</style>
