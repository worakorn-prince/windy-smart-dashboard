<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSecurityStore } from '@/stores/security'
import type { PersistedSecurityEvent } from '@/stores/security'

const store = useSecurityStore()
const loading = ref(false)
const error = ref('')
const LIMIT = 50

onMounted(() => {
  refresh()
})

async function refresh() {
  loading.value = true
  error.value = ''
  const res = await store.loadSecurityEvents(LIMIT)
  loading.value = false
  if (!res.ok) error.value = res.reason || 'Failed to load event history'
}

function formatTs(ts: string): string {
  const d = new Date(ts)
  return isNaN(d.getTime()) ? ts : d.toLocaleString()
}

const DETAIL_KEYS = ['ip', 'port', 'pid', 'name', 'user', 'country_code'] as const

function detailSummary(detail: PersistedSecurityEvent['detail']): string {
  if (!detail || typeof detail !== 'object') return ''
  const parts: string[] = []
  for (const key of DETAIL_KEYS) {
    const value = (detail as Record<string, unknown>)[key]
    if (value !== undefined && value !== null && value !== '') parts.push(`${key}=${String(value)}`)
  }
  let text = parts.join(', ')
  if (!text) {
    try {
      text = JSON.stringify(detail)
    } catch {
      text = String(detail)
    }
  }
  return text.length > 80 ? `${text.slice(0, 77)}…` : text
}
</script>

<template>
  <div class="card history-card">
    <h3>Security Event History</h3>
    <div class="actions">
      <button :disabled="loading" @click="refresh">{{ loading ? 'Loading…' : 'Refresh' }}</button>
      <span class="muted small">Last {{ store.securityEvents.length }} persisted events (newest first)</span>
      <span v-if="error" class="error small">{{ error }}</span>
    </div>
    <div v-if="store.securityEvents.length" class="table-wrap">
      <table>
        <thead>
          <tr><th>Time</th><th>Kind</th><th>Source IP</th><th>Detail</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in store.securityEvents" :key="e.id">
            <td class="small nowrap">{{ formatTs(e.ts) }}</td>
            <td class="small">{{ e.kind }}</td>
            <td class="small mono">{{ e.source_ip || '—' }}</td>
            <td class="small detail">{{ detailSummary(e.detail) || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted small">No persisted events yet.</p>
  </div>
</template>

<style scoped>
.history-card { width: 100%; }
.actions { display: flex; gap: 8px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
.error { color: var(--bad); }
.table-wrap { max-height: 320px; overflow-y: auto; }
.nowrap { white-space: nowrap; }
.mono { font-family: monospace; font-size: 11px; }
.detail { overflow-wrap: anywhere; }
table { width: 100%; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--border); }
th { font-size: 11px; color: var(--muted); text-transform: uppercase; }
</style>
