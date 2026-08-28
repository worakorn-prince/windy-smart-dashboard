<script setup lang="ts">
import { computed } from 'vue'
import { useSecurityStore } from '@/stores/security'

const store = useSecurityStore()

const labelClass = computed(() => {
  const label = (store.audit as any)?.risk_label?.toLowerCase() || 'low'
  return label
})

async function onRun() {
  await store.runAudit()
}

function onExport(fmt: 'pdf' | 'html' | 'json') {
  if (!store.audit) return
  store.exportReport(store.audit, fmt).catch((err) => alert(String(err)))
}
</script>

<template>
  <div class="card audit-card">
    <h3>Security Audit</h3>
    <p class="muted small">
      Inspects your machine for known weak-spots: open ports, Defender status,
      failed logins, hosts/redirects, ARP duplicates, suspicious outbound connections.
    </p>
    <div class="actions">
      <button class="primary" :disabled="store.auditRunning" @click="onRun">
        {{ store.auditRunning ? 'Running…' : 'Run Audit Now' }}
      </button>
    </div>

    <div v-if="store.audit" class="report">
      <div class="score">
        <div class="score-number">{{ store.audit.riskscore }}</div>
        <div class="score-label" :class="labelClass">{{ store.audit.risk_label }}</div>
      </div>

      <div class="summary">
        <div class="row small">
          <span class="label">Generated</span>
          <span class="value">{{ new Date(store.audit.generated_at).toLocaleString() }}</span>
        </div>
        <div class="row small">
          <span class="label">Duration</span>
          <span class="value">{{ store.audit.duration_ms }} ms</span>
        </div>
        <div class="row small">
          <span class="label">Findings</span>
          <span class="value">{{ store.audit.findings.length }}</span>
        </div>
      </div>

      <div class="export-buttons">
        <span class="muted small">Export:</span>
        <button @click="onExport('pdf')">PDF</button>
        <button @click="onExport('html')">HTML</button>
        <button @click="onExport('json')">JSON</button>
      </div>

      <div class="findings">
        <div v-for="(f, i) in store.audit.findings" :key="i" class="finding" :class="'sev-' + f.severity">
          <div class="finding-head">
            <span class="badge" :class="f.severity">{{ f.severity }}</span>
            <strong>{{ f.title }}</strong>
            <span class="weight">+{{ f.weight }}</span>
          </div>
          <p class="muted small">{{ f.description }}</p>
          <p class="muted small" v-if="f.category">Category: <span class="kbd">{{ f.category }}</span></p>
        </div>
        <p v-if="store.audit.findings.length === 0" class="muted">
          No findings - system looks healthy.
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.audit-card { grid-column: span 2; }
.actions { margin: 12px 0; }
.report { display: flex; flex-direction: column; gap: 16px; }
.score {
  display: flex; flex-direction: column; align-items: center;
  padding: 16px; border-radius: 10px; background: var(--panel-2);
}
.score-number { font-size: 38px; font-weight: 800; line-height: 1; }
.score-label { padding: 2px 12px; border-radius: 12px; margin-top: 4px; font-weight: 700; }
.score-label.low { background: var(--good); color: #082; }
.score-label.medium { background: var(--warn); color: #530; }
.score-label.high { background: var(--bad); color: #fff; }
.score-label.critical { background: var(--crit); color: #fff; }
.export-buttons { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.findings { display: flex; flex-direction: column; gap: 8px; }
.finding {
  padding: 10px; border-radius: 8px; background: var(--panel-2);
  border-left: 4px solid var(--muted);
}
.finding.sev-low { border-left-color: var(--good); }
.finding.sev-medium { border-left-color: var(--warn); }
.finding.sev-high { border-left-color: var(--bad); }
.finding.sev-critical { border-left-color: var(--crit); }
.finding-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.finding-head .weight { margin-left: auto; font-weight: 700; color: var(--muted); }
.finding p { margin: 4px 0 0; }
</style>