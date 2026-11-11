<script setup lang="ts">
import { onMounted } from 'vue'
import { useSecurityStore } from '@/stores/security'
import AuditCard from '@/components/security/AuditCard.vue'
import AuditHistoryCard from '@/components/security/AuditHistoryCard.vue'
import PortsCard from '@/components/security/PortsCard.vue'
import ConnectionsCard from '@/components/security/ConnectionsCard.vue'
import DefenderCard from '@/components/security/DefenderCard.vue'
import FailedLoginsCard from '@/components/security/FailedLoginsCard.vue'
import LiveEventsLog from '@/components/security/LiveEventsLog.vue'
import SecurityEventsLog from '@/components/security/SecurityEventsLog.vue'
import SettingsPanel from '@/components/security/SettingsPanel.vue'
import BlockedRulesCard from '@/components/security/BlockedRulesCard.vue'

const store = useSecurityStore()

const adminPill = 'Live'

onMounted(() => {
  store.connect()
})
</script>

<template>
  <div class="security-page">
    <header class="page-head">
      <div class="head-left">
        <p class="breadcrumb">SYSTEM / SECURITY</p>
        <h1>ความปลอดภัยของระบบ</h1>
        <p class="subtitle">พอร์ต, การเชื่อมต่อ, Defender และเหตุการณ์ที่บันทึกไว้</p>
      </div>
      <div class="head-right">
        <span class="status-pill">● {{ adminPill }}</span>
      </div>
    </header>

    <div class="callout small">
      <span>ℹ️ Some features (failed logins, kill process, block IP) require running as Administrator.</span>
    </div>

    <!-- Live events always visible at the top -->
    <div class="full-row">
      <LiveEventsLog />
    </div>

    <div class="grid">
      <AuditCard />
      <AuditHistoryCard />
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

    <!-- Persisted event history, right next to the settings grid -->
    <div class="full-row">
      <SecurityEventsLog />
    </div>
  </div>
</template>

<style scoped>
.security-page { display: flex; flex-direction: column; gap: 16px; }

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  flex-wrap: wrap;
}
.head-left { min-width: 0; }
.breadcrumb {
  margin: 0 0 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
}
.page-head h1 {
  margin: 0 0 4px;
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
}
.subtitle { margin: 0; font-size: 13px; color: var(--muted); }
.head-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel);
  font-size: 12px;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono);
  white-space: nowrap;
}

.callout {
  padding: 10px 14px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent-4);
  border-radius: var(--radius-ctl);
  color: var(--text-dim);
}

.full-row > :deep(.card) { width: 100%; }

@media (max-width: 900px) {
  .page-head { flex-direction: column; align-items: stretch; }
  .head-right { justify-content: flex-start; }
}
</style>