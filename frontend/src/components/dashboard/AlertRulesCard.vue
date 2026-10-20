<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMetricsStore } from '@/stores/metrics'
import type { AlertRulesPayload } from '@/stores/metrics'

const store = useMetricsStore()

const METRIC_LABELS: Record<string, string> = {
  cpu_temp: 'CPU Temp (°C)',
  gpu_temp: 'GPU Temp (°C)',
  ram_pct: 'RAM (%)',
  disk_pct: 'Disk (%)',
}

const draft = ref<AlertRulesPayload | null>(null)
const dirty = ref(false)
const savedFlash = ref(false)

function clone(v: AlertRulesPayload): AlertRulesPayload {
  return JSON.parse(JSON.stringify(v))
}

watch(() => store.alertRules, v => {
  if (v && !dirty.value) draft.value = clone(v)
}, { immediate: true })

onMounted(() => {
  if (!store.alertRules) store.loadAlertRules()
})

function markDirty() {
  dirty.value = true
  savedFlash.value = false
}

async function save() {
  if (!draft.value) return
  const ok = await store.saveAlertRules(clone(draft.value))
  if (ok) {
    dirty.value = false
    savedFlash.value = true
    window.setTimeout(() => { savedFlash.value = false }, 2500)
  }
}

const saveDisabled = computed(() => !draft.value || store.alertRulesSaving)
</script>

<template>
  <div class="card">
    <h3>Alert Rules</h3>
    <div v-if="!draft" class="muted small">{{ store.alertRulesError ?? 'Loading rules…' }}</div>
    <template v-else>
      <table class="rules">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Cond</th>
            <th>Limit</th>
            <th>On</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in draft.rules" :key="r.id">
            <td>{{ METRIC_LABELS[r.metric] ?? r.metric }}</td>
            <td>
              <select v-model="r.op" class="op" @change="markDirty">
                <option value=">=">≥</option>
                <option value=">">&gt;</option>
              </select>
            </td>
            <td>
              <input v-model.number="r.threshold" type="number" min="0" max="200"
                     step="1" class="limit" @input="markDirty" />
            </td>
            <td>
              <input v-model="r.enabled" type="checkbox" @change="markDirty" />
            </td>
          </tr>
        </tbody>
      </table>

      <div class="channels">
        <label class="ch">
          <input v-model="draft.channels.toast" type="checkbox" @change="markDirty" />
          Toast
        </label>
        <label class="ch">
          <input v-model="draft.channels.sound" type="checkbox" @change="markDirty" />
          Sound
        </label>
      </div>

      <div class="actions">
        <button class="save" :disabled="saveDisabled" @click="save">
          {{ store.alertRulesSaving ? 'Saving…' : 'Save' }}
        </button>
        <span v-if="savedFlash" class="ok small">Saved ✓</span>
        <span v-else-if="store.alertRulesError" class="err small">{{ store.alertRulesError }}</span>
        <span v-else-if="dirty" class="muted small">Unsaved changes</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.rules { width: 100%; border-collapse: collapse; font-size: 13px; }
.rules th { text-align: left; color: var(--muted); font-weight: 600; padding: 4px 6px; }
.rules td { padding: 4px 6px; border-top: 1px solid var(--border); }
.op, .limit { width: 100%; min-width: 0; background: var(--panel-2); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 4px 6px; }
.limit { width: 80px; }
.channels { display: flex; gap: 16px; margin-top: 10px; }
.ch { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.actions { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.save { cursor: pointer; }
.save:disabled { opacity: 0.5; cursor: default; }
.ok { color: var(--ok, #5fd97c); }
.err { color: #ff6b6b; }
.muted { color: var(--muted); }
.small { font-size: 12px; }
</style>
