<script setup lang="ts">
import { computed } from 'vue'
import { useInsightsStore } from '@/stores/insights'
import { formatGb, formatIsoText, formatSignedGb } from '@/utils/insights'
import InsightsCardShell from './InsightsCardShell.vue'

const store = useInsightsStore()

const rows = computed(() => store.data?.disk ?? [])
const ready = computed(() => store.data !== null && rows.value.length > 0)

const emptyText = computed(() => {
  if (store.data && !rows.value.length) {
    return 'ยังไม่มีข้อมูล disk_samples ในช่วงที่เลือก (เก็บเมื่อมีการใช้งานดิสก์)'
  }
  return 'ยังไม่มีข้อมูล disk_samples'
})

function usedPct(usedGb: number | null, totalGb: number | null): number | null {
  if (usedGb == null || totalGb == null || totalGb <= 0) return null
  return Math.min(100, (usedGb / totalGb) * 100)
}

function deltaClass(deltaGb: number | null): string {
  if (deltaGb == null || deltaGb === 0) return ''
  return deltaGb > 0 ? 'delta-up' : 'delta-down'
}
</script>

<template>
  <InsightsCardShell
    title="การเติบโตของดิสก์ (disk growth)"
    subtitle="ใช้งานต่อ mount จาก disk_samples — เวลาแสดงตามเขตเวลาเครื่อง"
    testid="insights-disk"
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
            <th>Mount</th>
            <th>ใช้ / ทั้งหมด</th>
            <th>เฉลี่ย</th>
            <th>สูงสุด</th>
            <th>ต้นช่วง → ล่าสุด</th>
            <th>เปลี่ยนแปลง</th>
            <th>ตัวอย่าง</th>
            <th>อัปเดตล่าสุด</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.mount">
            <td class="mount">{{ row.mount }}</td>
            <td>
              <div class="used-cell">
                <span>{{ formatGb(row.used_gb) }} / {{ formatGb(row.total_gb) }}</span>
                <span v-if="usedPct(row.used_gb, row.total_gb) !== null" class="bar">
                  <span
                    class="bar-fill"
                    :style="{ width: `${usedPct(row.used_gb, row.total_gb)!.toFixed(1)}%` }"
                  ></span>
                </span>
              </div>
            </td>
            <td>{{ formatGb(row.avg_used_gb) }}</td>
            <td>{{ formatGb(row.peak_used_gb) }}</td>
            <td>{{ formatGb(row.first_used_gb) }} → {{ formatGb(row.used_gb) }}</td>
            <td :class="deltaClass(row.delta_gb)" class="mono">{{ formatSignedGb(row.delta_gb) }}</td>
            <td class="mono">{{ row.n.toLocaleString() }}</td>
            <td class="mono">{{ formatIsoText(row.last_ts) }}</td>
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
.mount { color: var(--text); font-weight: 700; font-family: var(--font-mono, ui-monospace, monospace); }
.mono { font-family: var(--font-mono, ui-monospace, monospace); font-variant-numeric: tabular-nums; white-space: nowrap; }
.used-cell { display: flex; flex-direction: column; gap: 3px; min-width: 150px; }
.bar {
  height: 4px;
  border-radius: 999px;
  background: var(--panel-2);
  overflow: hidden;
  display: block;
}
.bar-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--accent), var(--accent-3));
}
.delta-up { color: var(--bad); font-weight: 600; }
.delta-down { color: var(--good); font-weight: 600; }
</style>
