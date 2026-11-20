<script setup lang="ts">
import { computed } from 'vue'
import { useInsightsStore } from '@/stores/insights'
import { formatNum, formatRatePct } from '@/utils/insights'
import InsightsCardShell from './InsightsCardShell.vue'

const store = useInsightsStore()

const maint = computed(() => store.data?.maintenance ?? null)
const ready = computed(() => maint.value !== null)
const hasRecords = computed(() => (maint.value?.total ?? 0) > 0)

const rateText = computed(() => formatRatePct(maint.value?.success_rate))
const okRatio = computed(() => {
  const m = maint.value
  if (!m || m.total <= 0) return null
  return (m.ok / m.total) * 100
})
</script>

<template>
  <InsightsCardShell
    title="สรุปการบำรุงรักษา"
    subtitle="นับจาก maintenance_actions — success_rate แสดงเป็น — เมื่อไม่มีข้อมูล"
    testid="insights-maintenance"
    :loading="store.loading"
    :ready="ready"
    :error="store.error"
    :empty="ready ? undefined : 'ยังไม่มีข้อมูล maintenance_actions'"
    @retry="store.load()"
  >
    <div class="tiles">
      <div class="tile" data-testid="insights-maint-total">
        <span class="tile-label">ทั้งหมด</span>
        <span class="tile-value">{{ formatNum(maint?.total) }}</span>
      </div>
      <div class="tile ok" data-testid="insights-maint-ok">
        <span class="tile-label">สำเร็จ</span>
        <span class="tile-value">{{ formatNum(maint?.ok) }}</span>
      </div>
      <div class="tile bad" data-testid="insights-maint-failed">
        <span class="tile-label">ล้มเหลว</span>
        <span class="tile-value">{{ formatNum(maint?.failed) }}</span>
      </div>
      <div class="tile" data-testid="insights-maint-rate">
        <span class="tile-label">Success rate</span>
        <span class="tile-value">{{ rateText ?? '—' }}</span>
      </div>
    </div>

    <p v-if="!hasRecords" class="no-records">ยังไม่มีการบันทึก action บำรุงรักษาในช่วงที่เลือก</p>

    <div v-if="okRatio !== null" class="ratio" role="img" :aria-label="`สำเร็จ ${okRatio.toFixed(1)}%`">
      <span class="ratio-fill" :style="{ width: `${okRatio.toFixed(1)}%` }"></span>
    </div>

    <div v-if="maint?.by_action?.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Action</th>
            <th>จำนวน</th>
            <th>สำเร็จ</th>
            <th>ล้มเหลว</th>
            <th>Success rate</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in maint.by_action" :key="row.action">
            <td class="mono name">{{ row.action }}</td>
            <td class="mono">{{ formatNum(row.count) }}</td>
            <td class="mono good">{{ formatNum(row.ok) }}</td>
            <td class="mono" :class="{ bad: row.failed > 0 }">{{ formatNum(row.failed) }}</td>
            <td class="mono">{{ formatRatePct(row.success_rate) ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </InsightsCardShell>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.tile {
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-ctl);
  background: var(--panel-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tile-label { font-size: 11px; color: var(--muted); }
.tile-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono, ui-monospace, monospace);
}
.tile.ok .tile-value { color: var(--good); }
.tile.bad .tile-value { color: var(--bad); }

.ratio {
  margin-top: 10px;
  height: 6px;
  border-radius: 999px;
  background: var(--panel-2);
  overflow: hidden;
}
.no-records { margin: 8px 0 0; font-size: 12px; color: var(--muted); }
.ratio-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--good), var(--accent));
}

.table-wrap { overflow-x: auto; margin-top: 12px; }
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
}
tbody tr:hover td { background: var(--accent-soft); }
.mono { font-family: var(--font-mono, ui-monospace, monospace); font-variant-numeric: tabular-nums; }
.name { color: var(--text); }
.good { color: var(--good); }
.bad { color: var(--bad); font-weight: 600; }
</style>
