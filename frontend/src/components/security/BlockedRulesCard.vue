<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSecurityStore } from '@/stores/security'

const store = useSecurityStore()
const blockedRules = ref<any[]>([])
const result = ref('')

onMounted(async () => {
  await refresh()
})

async function refresh() {
  const data = await store.listBlocked()
  blockedRules.value = data.rules || []
}

async function unblock(name: string) {
  const res = await store.unblockRule(name)
  result.value = res.ok ? `Removed ${name}` : `Failed: ${res.reason || 'unknown'}`
  await refresh()
  setTimeout(() => (result.value = ''), 4000)
}
</script>

<template>
  <div class="card">
    <h3>Firewall Block Rules</h3>
    <div class="actions">
      <button @click="refresh">Refresh</button>
      <span class="muted small" v-if="result">{{ result }}</span>
    </div>
    <table v-if="blockedRules.length">
      <thead>
        <tr><th>Name</th><th>IP</th><th>Act</th></tr>
      </thead>
      <tbody>
        <tr v-for="r in blockedRules" :key="r.name">
          <td class="small">{{ r.name }}</td>
          <td class="kbd">{{ r.ip }}</td>
          <td><button class="danger small-btn" @click="unblock(r.name)">Unblock</button></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted small">No block rules from this dashboard.</p>
  </div>
</template>

<style scoped>
.actions { display: flex; gap: 8px; align-items: center; margin: 8px 0; }
.small-btn { padding: 2px 6px; font-size: 11px; }
.kbd { font-family: monospace; font-size: 11px; }
</style>