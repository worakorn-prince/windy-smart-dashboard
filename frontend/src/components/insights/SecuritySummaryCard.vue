<script setup lang="ts">
import { computed } from 'vue'
import { useInsightsStore } from '@/stores/insights'
import { formatNum } from '@/utils/insights'
import InsightsCardShell from './InsightsCardShell.vue'

const store = useInsightsStore()

const security = computed(() => store.data?.security ?? null)
const ready = computed(() => security.value !== null && security.value.total > 0)

const emptyText = computed(() => {
  if (security.value && security.value.total === 0) {
    return 'ยังไม่มี security_events ในช่วงที่เลือก'
  }
  return 'ยังไม่มีข้อมูล security_events'
})
</script>

<template>
  <InsightsCardShell
    title="สรุปความปลอดภัย"
    subtitle="นับจาก security_events ในช่วงที่เลือก"
    testid="insights-security"
    :loading="store.loading"
    :ready="ready"
    :error="store.error"
    :empty="ready ? undefined : emptyText"
    @retry="store.load()"
  >
    <div class="total-row" data-testid="insights-security-total">
      <span class="total-label">เหตุการณ์ทั้งหมด</span>
      <span class="total-value">{{ formatNum(security?.total) }}</span>
    </div>

    <div v-if="security?.by_kind?.length" class="section">
      <h4>ตามประเภท (by kind)</h4>
      <ul class="chip-list">
        <li v-for="row in security.by_kind" :key="row.kind" class="chip">
          <span class="chip-kind">{{ row.kind }}</span>
          <span class="chip-count mono">{{ formatNum(row.count) }}</span>
        </li>
      </ul>
    </div>

    <div v-if="security?.top_sources?.length" class="section">
      <h4>แหล่งที่พบบ่อย (top source IPs)</h4>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Source IP</th>
              <th>จำนวน</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in security.top_sources" :key="row.source_ip">
              <td class="mono name">{{ row.source_ip }}</td>
              <td class="mono">{{ formatNum(row.count) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </InsightsCardShell>
</template>

<style scoped>
.total-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 10px;
}
.total-label { font-size: 12px; color: var(--muted); }
.total-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-variant-numeric: tabular-nums;
}
.section { margin-top: 12px; }
.section h4 {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}
.chip-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-2);
  font-size: 12px;
  color: var(--text-dim);
}
.chip-kind { color: var(--text); font-family: var(--font-mono, ui-monospace, monospace); }
.chip-count { color: var(--accent); font-weight: 700; }
.mono { font-family: var(--font-mono, ui-monospace, monospace); font-variant-numeric: tabular-nums; }
.table-wrap { overflow-x: auto; }
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
  padding: 5px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
}
tbody tr:hover td { background: var(--accent-soft); }
.name { color: var(--text); }
</style>
