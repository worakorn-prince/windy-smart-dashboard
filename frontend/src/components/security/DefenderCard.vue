<script setup lang="ts">
import { computed } from 'vue'
import { useSecurityStore } from '@/stores/security'

const store = useSecurityStore()

interface DefenderStatus {
  available: boolean
  reason?: string
  AMRunningMode?: string
  AntivirusEnabled?: boolean
  AntivirusSignatureLastUpdated?: string
  RealTimeProtectionEnabled?: boolean
  IsTamperProtected?: boolean
  BehaviorMonitorEnabled?: boolean
  NISEnabled?: boolean
  QuickScanEndTime?: string
  FullScanEndTime?: string
}

const defender = computed<DefenderStatus>(() => store.audit?.data?.defender ?? { available: false })

function fmtDate(d?: string): string {
  if (!d) return '-'
  try { return new Date(d).toLocaleString() } catch { return d }
}
</script>

<template>
  <div class="card">
    <h3>Windows Defender</h3>
    <div v-if="defender.available">
      <div class="row small">
        <span class="label">Real-time</span>
        <span class="value" :class="defender.RealTimeProtectionEnabled ? 'sev-low' : 'sev-high'">
          {{ defender.RealTimeProtectionEnabled ? 'ON' : 'OFF' }}
        </span>
      </div>
      <div class="row small">
        <span class="label">AV Enabled</span>
        <span class="value">{{ defender.AntivirusEnabled ? 'yes' : 'no' }}</span>
      </div>
      <div class="row small">
        <span class="label">Running Mode</span>
        <span class="value">{{ defender.AMRunningMode || '-' }}</span>
      </div>
      <div class="row small">
        <span class="label">Tamper Protect</span>
        <span class="value">{{ defender.IsTamperProtected ? 'on' : 'off' }}</span>
      </div>
      <div class="row small">
        <span class="label">Behavior Monitor</span>
        <span class="value">{{ defender.BehaviorMonitorEnabled ? 'on' : 'off' }}</span>
      </div>
      <div class="row small">
        <span class="label">Last Signature</span>
        <span class="value">{{ fmtDate(defender.AntivirusSignatureLastUpdated as any) }}</span>
      </div>
      <div class="row small">
        <span class="label">Last Quick Scan</span>
        <span class="value">{{ fmtDate(defender.QuickScanEndTime as any) }}</span>
      </div>
      <div class="row small">
        <span class="label">Last Full Scan</span>
        <span class="value">{{ fmtDate(defender.FullScanEndTime as any) }}</span>
      </div>
    </div>
    <p v-else-if="defender.reason" class="muted small">
      Not available: {{ defender.reason }}
    </p>
    <p v-else class="muted small">Run audit to populate.</p>
  </div>
</template>