<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useInsightsStore, type InsightsRange } from '@/stores/insights'
import { formatNaiveStamp } from '@/utils/insights'
import InsightsRangeTabs from '@/components/insights/InsightsRangeTabs.vue'
import TrendsCard from '@/components/insights/TrendsCard.vue'
import DiskGrowthCard from '@/components/insights/DiskGrowthCard.vue'
import TopProcessesCard from '@/components/insights/TopProcessesCard.vue'
import MaintenanceSummaryCard from '@/components/insights/MaintenanceSummaryCard.vue'
import SecuritySummaryCard from '@/components/insights/SecuritySummaryCard.vue'
import AnomaliesCard from '@/components/insights/AnomaliesCard.vue'

const store = useInsightsStore()

const generatedNote = computed(() => {
  const raw = store.data?.generated_at
  if (!raw) return null
  return `ข้อมูล ณ ${formatNaiveStamp(raw)} (เวลาเครื่อง)`
})

function setRange(r: InsightsRange): void {
  if (r !== store.range) void store.load(r)
}

onMounted(() => {
  void store.load()
})
</script>

<template>
  <div class="insights-page">
    <header class="page-head" data-testid="insights-head">
      <div class="head-left">
        <p class="breadcrumb">SYSTEM / INSIGHTS</p>
        <h1>ภาพรวมข้อมูลย้อนหลัง</h1>
        <p class="subtitle">สรุปแนวโน้ม, ดิสก์, โปรเซส, บำรุงรักษา และความปลอดภัยจาก history database</p>
      </div>
      <div class="head-right">
        <span v-if="generatedNote" class="generated-pill" data-testid="insights-generated">{{ generatedNote }}</span>
        <InsightsRangeTabs
          :model-value="store.range"
          :disabled="store.loading"
          @update:model-value="setRange"
        />
      </div>
    </header>

    <p v-if="store.error && !store.data" class="page-error" role="alert">
      โหลดข้อมูลภาพรวมไม่สำเร็จ: {{ store.error }}
    </p>

    <div class="full-row">
      <TrendsCard />
    </div>

    <div class="grid">
      <DiskGrowthCard />
      <TopProcessesCard />
    </div>

    <div class="grid">
      <MaintenanceSummaryCard />
      <SecuritySummaryCard />
    </div>

    <div class="full-row">
      <AnomaliesCard />
    </div>
  </div>
</template>

<style scoped>
.insights-page { display: flex; flex-direction: column; gap: 16px; }

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  flex-wrap: wrap;
}
.head-left { min-width: 0; }
.breadcrumb {
  margin: 0 0 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
}
.page-head h1 {
  margin: 0 0 4px;
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
}
.subtitle { margin: 0; font-size: 13px; color: var(--muted); }
.head-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.generated-pill {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel);
  font-size: 12px;
  color: var(--text-dim);
  font-family: var(--font-mono, ui-monospace, monospace);
  white-space: nowrap;
}

.page-error {
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--bad);
  border-radius: var(--radius-ctl);
  color: var(--bad);
  background: color-mix(in srgb, var(--bad) 8%, transparent);
  font-size: 13px;
}

.full-row > :deep(.card) { width: 100%; }

@media (max-width: 900px) {
  .page-head { flex-direction: column; align-items: stretch; }
  .head-right { justify-content: flex-start; }
}
</style>
