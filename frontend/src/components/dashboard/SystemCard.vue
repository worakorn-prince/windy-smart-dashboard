<script setup lang="ts">
import type { SystemInfo } from '@/stores/metrics'
import { computed } from 'vue'

const props = defineProps<{ system: SystemInfo | null }>()

const battery = computed(() => props.system?.battery ?? null)

const battColor = computed(() => {
  if (!battery.value) return ''
  if (battery.value.percent <= 15) return 'text-sev-critical'
  if (battery.value.percent <= 30) return 'text-sev-high'
  return battery.value.charging ? 'text-sev-low' : 'text-sev-medium'
})

function fmtTimeRemaining(secs: number | null): string {
  if (secs == null || secs < 0) return '—'
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}
</script>

<template>
  <div class="card">
    <h3>System</h3>
    <div v-if="system">
      <div class="row small">
        <span class="label">Hostname</span>
        <span class="value">{{ system.hostname }}</span>
      </div>
      <div class="row small">
        <span class="label">OS</span>
        <span class="value">{{ system.os_name }} {{ system.machine }}</span>
      </div>
      <div class="row small">
        <span class="label">Processor</span>
        <span class="value text-truncate" :title="system.processor">{{ system.processor }}</span>
      </div>
      <div class="row small">
        <span class="label">Uptime</span>
        <span class="value">{{ system.uptime }}</span>
      </div>
      <div class="row small">
        <span class="label">Boot time</span>
        <span class="value">{{ new Date(system.boot_time).toLocaleString() }}</span>
      </div>

      <!-- Battery -->
      <template v-if="battery">
        <hr style="border: 0; border-top: 1px solid var(--border); margin: 10px 0" />
        <h4>Battery</h4>
        <div class="row small">
          <span class="label">Charge</span>
          <span class="value" :class="battColor">
            {{ battery.percent }}% {{ battery.charging ? '⚡ Charging' : '' }}
          </span>
        </div>
        <div class="progress">
          <div :style="{ width: battery.percent + '%', background: battery.charging ? 'var(--good)' : 'var(--warn)' }"></div>
        </div>
        <div class="row small" v-if="battery.time_remaining && !battery.charging">
          <span class="label">Time remaining</span>
          <span class="value">{{ fmtTimeRemaining(battery.time_remaining) }}</span>
        </div>
        <div class="row small" v-if="battery.health_percent != null">
          <span class="label">Health</span>
          <span class="value">{{ battery.health_percent }}%</span>
        </div>
      </template>

      <hr style="border: 0; border-top: 1px solid var(--border); margin: 10px 0" />
      <div class="row small">
        <span class="label">Python</span>
        <span class="value">{{ system.python_version }}</span>
      </div>
    </div>
    <p v-else class="muted">Waiting for data…</p>
  </div>
</template>

<style scoped>
h4 {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.text-sev-low { color: var(--good); }
.text-sev-medium { color: var(--warn); }
.text-sev-high { color: var(--bad); }
.text-sev-critical { color: var(--crit); font-weight: 700; }
</style>