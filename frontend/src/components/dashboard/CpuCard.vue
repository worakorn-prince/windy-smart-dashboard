<script setup lang="ts">
import { computed } from 'vue'
import type { CpuSnapshot } from '@/stores/metrics'
import { formatNumber } from '@/composables/format'

const props = defineProps<{ cpu: CpuSnapshot | null; history: number[] }>()

const color = (v: number) => (v > 85 ? 'var(--bad)' : v > 60 ? 'var(--warn)' : 'var(--accent)')
const freqColor = (v: number | null) => (v && v > 3500 ? 'var(--warn)' : v && v < 1000 ? 'var(--info)' : 'var(--good)')

function tempClass(v: number) {
  if (v >= 85) return 'text-sev-critical'
  if (v >= 75) return 'text-sev-high'
  if (v >= 60) return 'text-sev-medium'
  return 'text-sev-low'
}
</script>

<template>
  <div class="card cpu-card">
    <h3>CPU</h3>
    <div v-if="cpu">
      <!-- Overall Usage -->
      <div class="section">
        <div class="row">
          <span class="label">Overall Usage</span>
          <span class="value"><strong :style="{ color: color(cpu.overall) }">{{ cpu.overall.toFixed(1) }}%</strong></span>
        </div>
        <div class="progress">
          <div :style="{ width: cpu.overall + '%', background: color(cpu.overall) }"></div>
        </div>
      </div>

      <!-- Per-Core Usage -->
      <div class="section" v-if="cpu.cores && cpu.cores.length > 0">
        <h4>Per-Core Usage</h4>
        <div class="cores-grid">
          <div v-for="(c, i) in cpu.cores" :key="i" class="core">
            <div class="core-bar">
              <div :style="{ height: c + '%', background: color(c) }"></div>
            </div>
            <span class="core-label">Core {{ i }}</span>
            <span class="core-value">{{ c.toFixed(1) }}%</span>
          </div>
        </div>
      </div>

      <!-- Frequency -->
      <div class="section" v-if="cpu.freq_mhz">
        <h4>Frequency</h4>
        <div class="freq-grid">
          <div class="freq-item">
            <span class="freq-label">Current</span>
            <span class="freq-value" :style="{ color: freqColor(cpu.freq_mhz.current) }">{{ cpu.freq_mhz.current ? (cpu.freq_mhz.current / 1000).toFixed(2) + ' GHz' : '—' }}</span>
          </div>
          <div class="freq-item">
            <span class="freq-label">Base</span>
            <span class="freq-value">{{ cpu.freq_mhz.min ? (cpu.freq_mhz.min / 1000).toFixed(2) + ' GHz' : '—' }}</span>
          </div>
          <div class="freq-item">
            <span class="freq-label">Boost</span>
            <span class="freq-value" :style="{ color: freqColor(cpu.freq_mhz.max) }">{{ cpu.freq_mhz.max ? (cpu.freq_mhz.max / 1000).toFixed(2) + ' GHz' : '—' }}</span>
          </div>
        </div>
      </div>

      <!-- CPU Info -->
      <div class="section" v-if="cpu.info">
        <h4>Processor Info</h4>
        <div class="info-grid">
          <div class="info-row">
            <span class="label">Model</span>
            <span class="value text-truncate" v-auto-tip>{{ cpu.info.Name }}</span>
          </div>
          <div class="info-row">
            <span class="label">Cores / Threads</span>
            <span class="value">{{ cpu.info.NumberOfCores }} / {{ cpu.info.NumberOfLogicalProcessors }}</span>
          </div>
          <div class="info-row">
            <span class="label">Max Clock</span>
            <span class="value">{{ cpu.info.MaxClockSpeed ? (cpu.info.MaxClockSpeed / 1000).toFixed(2) + ' GHz' : '—' }}</span>
          </div>
          <div class="info-row">
            <span class="label">L2 / L3 Cache</span>
            <span class="value">{{ cpu.info.L2CacheSize }} KB / {{ cpu.info.L3CacheSize }} KB</span>
          </div>
          <div class="info-row">
            <span class="label">Socket</span>
            <span class="value">{{ cpu.info.SocketDesignation }}</span>
          </div>
        </div>
      </div>

      <!-- Temperature -->
      <div class="section" v-if="cpu.temperature_celsius">
        <h4>Temperature</h4>
        <div class="temp-primary" v-if="cpu.temperature_celsius.primary != null">
          <span class="temp-primary-value" :class="tempClass(cpu.temperature_celsius.primary)">{{ cpu.temperature_celsius.primary.toFixed(1) }}°C</span>
          <span class="temp-primary-label">Package / Tctl-Tdie</span>
        </div>
        <div v-if="cpu.temperature_celsius.core_temps" class="temp-grid">
          <div v-for="(t, i) in cpu.temperature_celsius.core_temps" :key="t.name + i" class="temp-item">
            <span class="temp-label" v-auto-tip>{{ t.name }}</span>
            <span class="temp-value" :class="tempClass(t.value)">{{ t.value.toFixed(1) }}°C</span>
          </div>
        </div>
        <div class="temp-summary">
          <span class="label">Avg: {{ cpu.temperature_celsius.average.toFixed(1) }}°C</span>
          <span class="label">Max: {{ cpu.temperature_celsius.max.toFixed(1) }}°C</span>
        </div>
      </div>
      <div v-else class="muted small">Temperature unavailable — run dashboard as Administrator (uses LibreHardwareMonitor)</div>

      <!-- Power & Fan -->
      <div class="section" v-if="cpu.power_watts != null || cpu.fan_rpm != null">
        <h4>Power &amp; Cooling</h4>
        <div class="info-grid">
          <div class="info-row" v-if="cpu.power_watts != null">
            <span class="label">Power Draw</span>
            <span class="value">{{ cpu.power_watts.toFixed(1) }} W</span>
          </div>
          <div class="info-row" v-if="cpu.fan_rpm != null">
            <span class="label">Fan Speed</span>
            <span class="value">{{ cpu.fan_rpm }} RPM</span>
          </div>
        </div>
      </div>
      <div v-else class="muted small">Power/Fan data unavailable (requires LibreHardwareMonitor + admin)</div>

    </div>
    <p v-else class="muted">Waiting for data…</p>
  </div>
</template>

<style scoped>
.cpu-card { grid-column: span 2; }
.section { margin-bottom: 16px; }
.section h4 { margin: 0 0 8px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.cores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(60px, 1fr));
  gap: 8px;
  margin-top: 8px;
}
.core { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.core-bar {
  height: 60px;
  width: 100%;
  background: var(--panel-2);
  border-radius: 4px;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: flex-end;
}
.core-bar > div { width: 100%; transition: height 0.4s ease; }
.core-label { font-size: 10px; color: var(--muted); }
.core-value { font-size: 11px; font-weight: 600; color: var(--text); }

.freq-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 8px; }
.freq-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.freq-label { font-size: 10px; color: var(--muted); text-transform: uppercase; }
.freq-value { font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; }

.info-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; margin-top: 8px; }
.info-row { display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.info-row .label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.3px; }
.info-row .value { font-size: 12px; font-weight: 500; word-break: break-word; white-space: normal; line-height: 1.4; }

.temp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 8px; margin-top: 8px; }
.temp-primary {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 4px 0 10px;
}
.temp-primary-value { font-size: 30px; font-weight: 800; line-height: 1; }
.temp-primary-label { font-size: 11px; color: var(--muted); }
.temp-item { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px; background: var(--panel-2); border-radius: 6px; min-width: 0; }
.temp-label { font-size: 9px; color: var(--muted); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.temp-value { font-size: 14px; font-weight: 700; }
.temp-summary { display: flex; justify-content: space-around; margin-top: 8px; font-size: 11px; color: var(--muted); }

.text-sev-low { color: var(--good); }
.text-sev-medium { color: var(--warn); }
.text-sev-high { color: var(--bad); }
.text-sev-critical { color: var(--crit); font-weight: 700; }
</style>