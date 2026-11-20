<script setup lang="ts">
import { INSIGHTS_RANGES, type InsightsRange } from '@/stores/insights'

const RANGE_LABELS: Record<InsightsRange, string> = {
  '24h': '24 ชม.',
  '7d': '7 วัน',
  '30d': '30 วัน',
}

defineProps<{ modelValue: InsightsRange; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: InsightsRange] }>()
</script>

<template>
  <div class="ranges" data-testid="insights-range-tabs" role="tablist" aria-label="ช่วงเวลา">
    <button
      v-for="r in INSIGHTS_RANGES"
      :key="r"
      type="button"
      role="tab"
      class="range-btn"
      :class="{ active: modelValue === r }"
      :aria-selected="modelValue === r"
      :disabled="disabled"
      :data-testid="`insights-range-${r}`"
      @click="emit('update:modelValue', r)"
    >{{ RANGE_LABELS[r] }}</button>
  </div>
</template>

<style scoped>
.ranges {
  display: flex;
  gap: 6px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px;
}
.range-btn {
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  font-family: var(--font-mono, ui-monospace, monospace);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.range-btn:hover { color: var(--text); border-color: var(--border-strong); }
.range-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 700;
}
.range-btn:disabled { opacity: 0.6; cursor: wait; }
</style>
