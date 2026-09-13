<script setup lang="ts">
import { useMetricsStore } from '@/stores/metrics'

const store = useMetricsStore()
</script>

<template>
  <div class="card">
    <h3>Alerts ({{ store.alerts.length }})</h3>
    <div v-if="store.alerts.length === 0" class="muted small">No active alerts.</div>
    <div v-else class="rows">
      <div v-for="a in store.alerts" :key="a.uid" class="row">
        <div class="body">
          <div class="title">{{ a.title }}</div>
          <div class="msg muted small">{{ a.message }}</div>
        </div>
        <button class="x" title="Dismiss" @click="store.dismissAlert(a.uid!)">×</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rows { display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.title { font-weight: 600; }
.muted { color: var(--muted); }
.small { font-size: 12px; }
.x { cursor: pointer; }
</style>
