<script setup lang="ts">
import { onMounted } from 'vue'
import { useSecurityStore } from '@/stores/security'
import AuditCard from '@/components/security/AuditCard.vue'
import PortsCard from '@/components/security/PortsCard.vue'
import ConnectionsCard from '@/components/security/ConnectionsCard.vue'
import DefenderCard from '@/components/security/DefenderCard.vue'
import FailedLoginsCard from '@/components/security/FailedLoginsCard.vue'
import SecurityEventsLog from '@/components/security/SecurityEventsLog.vue'
import SettingsPanel from '@/components/security/SettingsPanel.vue'
import BlockedRulesCard from '@/components/security/BlockedRulesCard.vue'

const store = useSecurityStore()

onMounted(() => {
  store.connect()
})
</script>

<template>
  <div class="security-page">
    <div class="banner muted small">
      <span>ℹ️ Some features (failed logins, kill process, block IP) require running as Administrator.</span>
    </div>

    <!-- Live events always visible at the top -->
    <div class="full-row">
      <SecurityEventsLog />
    </div>

    <div class="grid">
      <AuditCard />
      <DefenderCard />
    </div>

    <!-- Wide tables get their own full-width rows so columns stay readable -->
    <div class="full-row">
      <PortsCard />
    </div>
    <div class="full-row">
      <ConnectionsCard />
    </div>
    <div class="full-row">
      <FailedLoginsCard />
    </div>

    <div class="grid">
      <BlockedRulesCard />
      <SettingsPanel />
    </div>
  </div>
</template>

<style scoped>
.security-page { display: flex; flex-direction: column; gap: 16px; }
.banner { padding: 8px 12px; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; }
.full-row > :deep(.card) { width: 100%; }
</style>