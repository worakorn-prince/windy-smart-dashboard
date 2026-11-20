<script setup lang="ts">
import { computed } from 'vue'
import { useInsightsStore, type TrendMetric } from '@/stores/insights'
import { formatEpochSec, formatNum } from '@/utils/insights'
import InsightsCardShell from './InsightsCardShell.vue'

const store = useInsightsStore()

const METRIC_LABELS: Record<TrendMetric, string> = {
  cpu_pct: 'CPU %',
  ram_pct: 'RAM %',
  swap_pct: 'Swap %',
  cpu_temp: 'CPU °C',
  gpu_temp: 'GPU °C',
  disk_temp_max: 'Disk °C',
  cpu_power_w: 'CPU W',
  gpu_power_w: 'GPU W',
  net_sent_bps: 'Net ↑',
  net_recv_bps: 'Net ↓',
  disk_read_bps: 'Disk R',
  disk_write_bps: 'Disk W',
}

function metricLabel(metric: string): string {
  return METRIC_LABELS[metric as TrendMetric] ?? metric
}

const rows = computed(() => store.data?.anomalies ?? [])
const ready = computed(() => store.data !== null && rows.value.length > 0)

const emptyText = computed(() => {
  if (store.data && !rows.value.length) {
    return 'ไม่พบ anomaly ในช่วงนี้ (ค่าอยู่ใน baseline ±3σ ติดต่อกัน)'
  }
  return 'ยังไม่มีข้อมูล baseline/anomalies'
})

function fmtMetricValue(metric: string, value: number | null): string {
  if (value == null) return '—'
  if (metric.endsWith('_bps')) return `${(value / (1024 * 1024)).toFixed(2)} MB/s`
  if (metric.endsWith('_pct')) return `${value.toFixed(1)}%`
  if (metric.endsWith('_temp')) return `${value.toFixed(1)}°C`
  if (metric.endsWith('_w')) return `${value.toFixed(1)} W`
  return value.toFixed(2)
}
</script>

<template>
  <InsightsCardShell
    title="ความผิดปกติ (anomalies)"
    subtitle="ตรวจด้วย z-score ≥ 3 ติดต่อกัน 3 ตัวอย่าง — เทียบกับ baseline รายชั่วโมง"
    testid="insights-anomalies"
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
            <th>เวลา</th>
            <th>Metric</th>
            <th>ค่าที่วัด</th>
            <th>คาดหมาย</th>
            <th>z</th>
            <th>ทิศทาง</th>
            <th>ต่อเนื่อง</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="`${row.metric}-${row.ts}-${i}`">
            <td class="mono">{{ formatEpochSec(row.ts) }}</td>
            <td class="name">{{ metricLabel(row.metric) }}</td>
            <td class="mono" :class="row.direction === 'high' ? 'up' : 'down'">
              {{ fmtMetricValue(row.metric, row.value) }}
            </td>
            <td class="mono muted">{{ fmtMetricValue(row.metric, row.expected) }}</td>
            <td class="mono">{{ formatNum(row.z, 2) }}</td>
            <td>
              <span class="badge" :class="row.direction === 'high' ? 'high' : 'low'">
                {{ row.direction === 'high' ? '▲ สูงกว่าปกติ' : '▼ ต่ำกว่าปกติ' }}
              </span>
            </td>
            <td class="mono">{{ formatNum(row.run_len) }} ตัวอย่าง</td>
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
.name { color: var(--text); font-weight: 600; white-space: nowrap; }
.up { color: var(--bad); font-weight: 600; }
.down { color: var(--info); font-weight: 600; }
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.badge.high {
  background: color-mix(in srgb, var(--bad) 14%, transparent);
  color: var(--bad);
}
.badge.low {
  background: color-mix(in srgb, var(--info) 14%, transparent);
  color: var(--info);
}
</style>
