<script setup lang="ts">
import { computed } from 'vue'
import type { RamSnapshot } from '@/stores/metrics'
import { formatBytes } from '@/composables/format'

const props = defineProps<{ ram: RamSnapshot | null; history: number[] }>()

const color = (v: number) => (v > 90 ? 'var(--bad)' : v > 75 ? 'var(--warn)' : 'var(--accent)')
const used = computed(() => formatBytes(props.ram?.used ?? 0))
const total = computed(() => formatBytes(props.ram?.total ?? 0))
const available = computed(() => formatBytes(props.ram?.available ?? 0))
const swap = computed(() => {
  if (!props.ram || !props.ram.swap_total) return null
  return `${formatBytes(props.ram.swap_used)} / ${formatBytes(props.ram.swap_total)} (${props.ram.swap_percent}%)`
})

function tempClass(v: number) {
  if (v >= 60) return 'text-sev-critical'
  if (v >= 50) return 'text-sev-high'
  if (v >= 40) return 'text-sev-medium'
  return 'text-sev-low'
}
</script>

<template>
  <div class="card">
    <h3>Memory</h3>
    <div v-if="ram">
      <div class="section">
        <div class="row">
          <span class="label">Usage</span>
          <span class="value"><strong :style="{ color: color(ram.percent) }">{{ ram.percent.toFixed(1) }}%</strong></span>
        </div>
        <div class="progress">
          <div :style="{ width: ram.percent + '%', background: color(ram.percent) }"></div>
        </div>
        <div class="row small">
          <span class="label">Used / Total</span>
          <span class="value">{{ used }} / {{ total }}</span>
        </div>
        <div class="row small">
          <span class="label">Available</span>
          <span class="value">{{ available }}</span>
        </div>
        <div class="row small" v-if="swap">
          <span class="label">Swap</span>
          <span class="value">{{ swap }}</span>
        </div>
      </div>

      <!-- RAM Details -->
      <div class="section" v-if="ram.details">
        <h4>Memory Details</h4>
        <div class="info-grid">
          <div class="info-row">
            <span class="label">Type</span>
            <span class="value"><strong>{{ ram.details.type }}</strong></span>
          </div>
          <div class="info-row">
            <span class="label">Channels</span>
            <span class="value">{{ ram.details.channels }} Channel{{ ram.details.channels > 1 ? 's' : '' }}</span>
          </div>
          <div class="info-row">
            <span class="label">Max Speed</span>
            <span class="value">{{ ram.details.max_speed_mhz }} MHz</span>
          </div>
          <div class="info-row">
            <span class="label">Total Capacity</span>
            <span class="value">{{ ram.details.total_capacity_gb }} GB</span>
          </div>
        </div>

        <!-- Modules -->
        <div v-if="ram.details.modules && ram.details.modules.length > 0" class="modules-section">
          <h4>Modules</h4>
          <table>
            <thead>
              <tr>
                <th>Slot</th>
                <th>Capacity</th>
                <th>Type</th>
                <th>Speed</th>
                <th>Manufacturer</th>
                <th>Part Number</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(m, i) in ram.details.modules" :key="i">
                <td class="value">{{ m.location || m.bank || `Slot ${i}` }}</td>
                <td class="value">{{ m.capacity_gb }} GB</td>
                <td class="value">{{ m.type }}</td>
                <td class="value">{{ m.speed_mhz }} MHz</td>
                <td class="muted small text-truncate" :title="m.manufacturer">{{ m.manufacturer }}</td>
                <td class="muted small text-truncate" :title="m.part_number">{{ m.part_number }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Temperature -->
      <div class="section" v-if="ram.temperature_celsius">
        <h4>Temperature</h4>
        <div v-if="ram.temperature_celsius.temps" class="temp-grid">
          <div v-for="(t, i) in ram.temperature_celsius.temps" :key="t.name + i" class="temp-item">
            <span class="temp-label" v-auto-tip>{{ t.name }}</span>
            <span class="temp-value" :class="tempClass(t.value)">{{ t.value.toFixed(1) }}°C</span>
          </div>
        </div>
        <div class="temp-summary">
          <span class="label">Max: {{ ram.temperature_celsius.max.toFixed(1) }}°C</span>
        </div>
      </div>
      <div v-else class="muted small">Temperature unavailable (requires LibreHardwareMonitor + admin)</div>

      <!-- Voltage -->
      <div class="section" v-if="ram.voltage != null">
        <h4>Voltage</h4>
        <div class="row">
          <span class="label">Memory Voltage</span>
          <span class="value">{{ ram.voltage.toFixed(3) }} V</span>
        </div>
      </div>
      <div v-else class="muted small">Voltage data unavailable (requires LibreHardwareMonitor + admin)</div>

      <!-- Swap -->
      <div class="section" v-if="ram.swap_total > 0">
        <h4>Swap</h4>
        <div class="row">
          <span class="label">Usage</span>
          <span class="value"><strong>{{ ram.swap_percent }}%</strong></span>
        </div>
        <div class="progress">
          <div :style="{ width: ram.swap_percent + '%', background: 'var(--info)' }"></div>
        </div>
        <div class="row small">
          <span class="label">Used / Total</span>
          <span class="value">{{ formatBytes(ram.swap_used) }} / {{ formatBytes(ram.swap_total) }}</span>
        </div>
      </div>
    </div>
    <p v-else class="muted">Waiting for data…</p>
  </div>
</template>

<style scoped>
.section { margin-bottom: 16px; }
.section h4 { margin: 0 0 8px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.info-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; margin-top: 8px; }
.info-row { display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.info-row .label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.3px; }
.info-row .value { font-size: 12px; font-weight: 500; word-break: break-word; white-space: normal; line-height: 1.4; }

.modules-section { margin-top: 12px; }
.modules-section h4 { margin: 0 0 8px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.modules-section table { font-size: 11px; }
.modules-section th { color: var(--muted); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.3px; }

.temp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 8px; margin-top: 8px; }
.temp-item { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px; background: var(--panel-2); border-radius: 6px; min-width: 0; }
.temp-label { font-size: 9px; color: var(--muted); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.temp-value { font-size: 14px; font-weight: 700; }
.temp-summary { margin-top: 8px; font-size: 11px; color: var(--muted); }

.text-sev-low { color: var(--good); }
.text-sev-medium { color: var(--warn); }
.text-sev-high { color: var(--bad); }
.text-sev-critical { color: var(--crit); font-weight: 700; }
</style>