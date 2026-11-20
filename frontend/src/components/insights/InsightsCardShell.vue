<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
  testid?: string
  loading?: boolean
  ready?: boolean
  error?: string | null
  empty?: string
}>()

defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="card insights-card" :data-testid="testid">
    <div class="head">
      <div class="head-text">
        <h3 class="card-title">{{ title }}</h3>
        <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
      </div>
      <div class="head-actions">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="error" class="state error-state" role="alert">
      <p>โหลดไม่สำเร็จ: {{ error }}</p>
      <button type="button" class="retry-btn" @click="$emit('retry')">ลองใหม่</button>
    </div>
    <p v-else-if="loading && !ready" class="state">กำลังโหลด…</p>
    <p v-else-if="!ready || empty" class="state">{{ empty || 'ยังไม่มีข้อมูลในช่วงนี้' }}</p>
    <slot v-else />
  </div>
</template>

<style scoped>
.insights-card { min-width: 0; }
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.head-text { min-width: 0; }
.card-title {
  margin: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 0.02em;
  text-transform: none;
  white-space: normal;
}
.subtitle { margin: 4px 0 0; font-size: 12px; color: var(--muted); }
.head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.state {
  margin: 10px 0 0;
  padding: 14px 12px;
  border: 1px dashed var(--border);
  border-radius: var(--radius-ctl);
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}
.error-state {
  border-style: solid;
  border-color: var(--bad);
  color: var(--bad);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  text-align: left;
}
.error-state p { margin: 0; }
.retry-btn {
  background: var(--panel-2);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-ctl);
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  padding: 4px 12px;
  cursor: pointer;
}
.retry-btn:hover { border-color: var(--accent); color: var(--accent); }
</style>
