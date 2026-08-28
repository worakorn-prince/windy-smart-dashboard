<script setup lang="ts">
import { useMetricsStore } from '@/stores/metrics'

const store = useMetricsStore()

function iconFor(title: string): string {
  const t = title.toLowerCase()
  if (t.includes('temperature')) return '🌡️'
  if (t.includes('disk')) return '💾'
  if (t.includes('ram')) return '🧠'
  return '⚠️'
}
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="a in store.alerts" :key="a.uid" class="toast" @click="store.dismissAlert(a.uid!)">
        <span class="icon">{{ iconFor(a.title) }}</span>
        <div class="body">
          <div class="title">{{ a.title }}</div>
          <div class="msg">{{ a.message }}</div>
        </div>
        <button class="x" title="Dismiss" @click.stop="store.dismissAlert(a.uid!)">×</button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed; top: 16px; right: 16px; z-index: 1000;
  display: flex; flex-direction: column; gap: 10px; width: 320px;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  display: flex; align-items: flex-start; gap: 10px;
  background: var(--panel); border: 1px solid var(--warn);
  border-radius: 12px; padding: 12px 14px;
  box-shadow: 0 8px 24px rgba(0,0,0,.45);
  cursor: pointer;
}
.icon { font-size: 18px; line-height: 1.2; }
.body { flex: 1; min-width: 0; }
.title { font-weight: 600; font-size: 13px; color: var(--text); }
.msg { font-size: 12px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
.x {
  background: transparent; border: none; color: var(--muted);
  font-size: 16px; cursor: pointer; padding: 0 2px; line-height: 1;
}
.x:hover { color: var(--text); }

.toast-enter-active, .toast-leave-active { transition: all .25s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(24px); }
</style>
