<script setup lang="ts">
import { useSecurityStore } from '@/stores/security'
import { timeAgo } from '@/composables/format'

const store = useSecurityStore()

function iconFor(type: string): string {
  if (type.includes('port_opened')) return '🚪'
  if (type.includes('port_closed')) return '🚪'
  if (type.includes('outbound')) return '🌐'
  if (type.includes('suspicious')) return '⚠️'
  if (type.includes('tor')) return '🧅'
  if (type.includes('failed_login')) return '🚫'
  if (type.includes('defender_disabled')) return '🛑'
  if (type.includes('defender_enabled')) return '✅'
  return '•'
}

function classFor(type: string): string {
  if (type.includes('suspicious') || type.includes('tor') || type.includes('defender_disabled') || type.includes('failed_login')) return 'sev-high'
  if (type.includes('defender_enabled')) return 'sev-low'
  return ''
}
</script>

<template>
  <div class="card events-card">
    <h3>Live Security Events</h3>
    <p class="muted small">Pushed via WebSocket. Persists only while the page is open.</p>
    <div class="events-list">
      <div v-for="(e, i) in store.events" :key="i" class="event" :class="classFor((e as any).event_type || e.type)">
        <span class="icon">{{ iconFor((e as any).event_type || e.type) }}</span>
        <div class="body">
          <div class="title">{{ e.title }}</div>
          <div class="meta muted small">
            {{ (e as any).event_type || e.type }} · {{ timeAgo(e.timestamp) }}
          </div>
        </div>
      </div>
      <p v-if="store.events.length === 0" class="muted small">No events yet.</p>
    </div>
  </div>
</template>

<style scoped>
.events-card { max-height: 360px; display: flex; flex-direction: column; width: 100%; }
.events-list { flex: 1; overflow-y: auto; padding-right: 4px; }
.event {
  display: flex; gap: 8px; padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
.event .icon { font-size: 16px; }
.event .body { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.event .title { font-size: 12px; word-break: break-word; }
.event.sev-high .title { color: var(--bad); }
.event.sev-low .title { color: var(--good); }
.event .meta { font-size: 10px; }

/* Two-column layout on wide screens so the log uses the full width */
@media (min-width: 900px) {
  .events-list {
    columns: 2;
    column-gap: 16px;
  }
  .event { break-inside: avoid; }
}
</style>