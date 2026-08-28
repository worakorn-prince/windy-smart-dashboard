<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useSecurityStore } from '@/stores/security'

const store = useSecurityStore()
const input = ref('')
const saving = ref(false)
const lastSaved = ref('')

onMounted(async () => {
  await store.loadSuspicious()
  input.value = store.suspiciousCountries.join(', ')
})

async function save() {
  saving.value = true
  const list = input.value
    .split(/[,\s\n]+/)
    .map(s => s.trim().toUpperCase().slice(0, 2))
    .filter(s => s.length === 2 && /[A-Z]{2}/.test(s))
  const res = await store.saveSuspicious(list)
  saving.value = false
  lastSaved.value = res.ok ? `Saved ${list.length} countries` : `Failed: ${res.reason || 'unknown'}`
  input.value = store.suspiciousCountries.join(', ')
  setTimeout(() => (lastSaved.value = ''), 4000)
}
</script>

<template>
  <div class="card settings-card">
    <h3>Suspicious Countries Watchlist</h3>
    <p class="muted small">
      ISO-3166 country codes (2 letters). Outbound connections to these countries
      are flagged in the audit and in the live event log.
    </p>
    <input
      v-model="input"
      type="text"
      placeholder="RU, CN, KP, IR, BY, TR, UA"
      class="input"
    />
    <div class="actions">
      <button class="primary" :disabled="saving" @click="save">
        {{ saving ? 'Saving…' : 'Save' }}
      </button>
      <span class="muted small" v-if="lastSaved">{{ lastSaved }}</span>
    </div>
  </div>
</template>

<style scoped>
.input {
  width: 100%; padding: 6px 10px; background: var(--panel-2);
  color: var(--text); border: 1px solid var(--border); border-radius: 6px;
  font-family: monospace; font-size: 13px;
}
.actions { display: flex; gap: 8px; align-items: center; margin-top: 8px; }
</style>