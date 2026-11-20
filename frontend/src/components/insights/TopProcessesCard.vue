<script setup lang="ts">
import { computed } from 'vue'
import { useInsightsStore } from '@/stores/insights'
import { formatMemMb, formatNum } from '@/utils/insights'
import InsightsCardShell from './InsightsCardShell.vue'

const store = useInsightsStore()

const rows = computed(() => store.data?.top_processes ?? [])
const ready = computed(() => store.data !== null && rows.value.length > 0)

const emptyText = computed(() => {
  if (store.data && !rows.value.length) {
    return 'ยังไม่มีข้อมูล process_samples ในช่วงที่เลือก'
  }
  return 'ยังไม่มีข้อมูล process_samples'
})
</script>

<template>
  <InsightsCardShell
    title="โปรเซสที่ใช้ CPU เฉลี่ยสูงสุด"
    subtitle="ค่าเฉลี่ย CPU และหน่วยความจำสูงสุด จัดกลุ่มตามชื่อโปรเซส"
    testid="insights-processes"
    :loading="store.loading"
    :ready="ready"
    :error="store.error"
    :empty="ready ? undefined : emptyText"
    @retry="store.load()"
  >
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>โปรเซส</th>
            <th>CPU เฉลี่ย</th>
            <th>RAM สูงสุด</th>
            <th>ตัวอย่าง</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="row.name">
            <td class="mono muted">{{ i + 1 }}</td>
            <td class="name">{{ row.name }}</td>
            <td class="mono">{{ formatNum(row.avg_cpu_pct, 2) }}%</td>
            <td class="mono">{{ formatMemMb(row.peak_mem_mb) }}</td>
            <td class="mono muted">{{ formatNum(row.n) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </InsightsCardShell>
</template>

<style scoped>
.table-wrap { overflow-x: auto; margin-top: 10px; }
table { width: 100%; font-size: 12px; }
th {
  text-align: left;
  color: var(--muted);
  font-weight: 600;
  padding: 4px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  vertical-align: middle;
}
tbody tr:hover td { background: var(--accent-soft); }
.mono { font-family: var(--font-mono, ui-monospace, monospace); font-variant-numeric: tabular-nums; white-space: nowrap; }
.muted { color: var(--muted); }
.name {
  color: var(--text);
  font-family: var(--font-mono, ui-monospace, monospace);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
