<script setup lang="ts">
import type { ProcessInfo } from '@/stores/metrics'

defineProps<{ processes: ProcessInfo[]; selectedPid?: number | null }>()
const emit = defineEmits<{ select: [pid: number] }>()

function truncateName(name: string, max = 22): string {
  if (!name) return ''
  return name.length > max ? name.slice(0, max - 1) + '…' : name
}
</script>

<template>
  <div class="card">
    <h3>Top Processes</h3>
    <table v-if="processes.length">
      <thead>
        <tr>
          <th>PID</th>
          <th>Name</th>
          <th>User</th>
          <th>CPU%</th>
          <th>RAM%</th>
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
          <td class="value">{{ p.pid }}</td>
          <td>{{ truncateName(p.name) }}</td>
          <td class="muted small" :title="p.user">{{ truncateName(p.user || '', 14) }}</td>
          <td class="value">{{ p.cpu.toFixed(1) }}</td>
          <td class="value">{{ p.ram_percent.toFixed(1) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Waiting for data…</p>
  </div>
</template>

<style scoped>
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: rgba(124, 156, 255, 0.08); }
tr.clickable:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
tr.selected { background: rgba(124, 156, 255, 0.16); }
</style>
