<script setup lang="ts">
import type { GpuSnapshot } from '@/stores/metrics'
import { useMetricsStore } from '@/stores/metrics'
import { computed } from 'vue'

const props = defineProps<{ gpu: GpuSnapshot | null }>()
const store = useMetricsStore()
const sensorMsg = computed(() => store.sensorStatus?.message ?? '')
const noLiveSensors = computed(() => {
  const gpus = props.gpu?.gpus ?? []
  if (!gpus.length) return false
  return gpus.every(
    (g) => g.temperature_celsius == null && g.fan_speed_percent == null,
  )
})

const tempColor = (v?: number) => {
  if (v == null) return ''
  if (v >= 85) return 'text-sev-critical'
  if (v >= 75) return 'text-sev-high'
  if (v >= 60) return 'text-sev-medium'
  return 'text-sev-low'
}

const vendorIcon = (v: string) => {
  if (v === 'NVIDIA') return '🟢'
  if (v === 'AMD') return '🔴'
  if (v === 'Intel') return '🔵'
  return '🎮'
}
</script>

<template>
  <div class="card">
    <h3>GPU</h3>
    <div v-if="gpu && gpu.gpus.length > 0">
      <div v-for="(g, i) in gpu.gpus" :key="i" class="gpu-block">
        <div class="gpu-header">
          <span class="gpu-name" v-auto-tip>{{ vendorIcon(g.vendor) }} {{ g.name }}</span>
          <span class="badge">{{ g.vendor }}</span>
        </div>

        <!-- Real-time metrics (NVIDIA via nvidia-smi) -->
        <div v-if="g.gpu_usage_percent !== undefined" class="usage-section">
          <div class="row small">
            <span class="label">Core Usage</span>
            <span class="value"><strong>{{ g.gpu_usage_percent }}%</strong></span>
          </div>
          <div class="progress">
            <div :style="{ width: (g.gpu_usage_percent || 0) + '%' }"></div>
          </div>
          <div class="row small" v-if="g.vram_total_mb">
            <span class="label">VRAM</span>
            <span class="value">{{ g.vram_used_mb }} / {{ g.vram_total_mb }} MB</span>
          </div>
          <div class="progress" v-if="g.vram_total_mb">
            <div :style="{ width: ((g.vram_used_mb || 0) / g.vram_total_mb * 100) + '%', background: 'var(--info)' }"></div>
          </div>
        </div>

        <!-- Details grid -->
        <div class="info-grid">
          <div class="info-row" v-if="g.vram_total_mb != null">
            <span class="label">VRAM Total</span>
            <span class="value">{{ (g.vram_total_mb / 1024).toFixed(1) }} GB</span>
          </div>
          <div class="info-row" v-if="g.driver_version">
            <span class="label">Driver</span>
            <span class="value text-truncate" :title="g.driver_version">{{ g.driver_version }}</span>
          </div>
          <div class="info-row" v-if="g.temperature_celsius != null">
            <span class="label">Temp</span>
            <span class="value" :class="tempColor(g.temperature_celsius)">{{ g.temperature_celsius }}°C</span>
          </div>
          <div class="info-row" v-if="(g as any).hotspot_temp != null">
            <span class="label">Hotspot</span>
            <span class="value" :class="tempColor((g as any).hotspot_temp)">{{ (g as any).hotspot_temp }}°C</span>
          </div>
          <div class="info-row" v-if="g.power_draw_watts != null">
            <span class="label">Power</span>
            <span class="value">{{ g.power_draw_watts }} W</span>
          </div>
          <div class="info-row" v-if="g.graphics_clock_mhz != null">
            <span class="label">Core Clock</span>
            <span class="value">{{ g.graphics_clock_mhz }} MHz</span>
          </div>
          <div class="info-row" v-if="g.memory_clock_mhz != null">
            <span class="label">Mem Clock</span>
            <span class="value">{{ g.memory_clock_mhz }} MHz</span>
          </div>
          <div class="info-row" v-if="g.fan_speed_percent != null">
            <span class="label">Fan</span>
            <span class="value">{{ g.fan_speed_percent }}%</span>
          </div>
          <div class="info-row" v-if="g.resolution">
            <span class="label">Resolution</span>
            <span class="value">{{ g.resolution }} @ {{ g.refresh_rate }}Hz</span>
          </div>
        </div>
      </div>
    </div>
    <p v-else class="muted">No dedicated GPU detected.</p>
    <p v-if="noLiveSensors && sensorMsg" class="muted small">{{ sensorMsg }}</p>
  </div>
</template>

<style scoped>
.gpu-block {
  padding: 10px;
  background: var(--panel-2);
  border-radius: 8px;
  margin-bottom: 12px;
}
.gpu-block:last-child { margin-bottom: 0; }
.gpu-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.gpu-name {
  font-weight: 600;
  font-size: 13px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.usage-section { margin-bottom: 10px; }

.info-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; }
.info-row { display: flex; flex-direction: column; gap: 2px; min-width: 0; overflow-wrap: anywhere; }
.info-row .label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.3px; }
.info-row .value { font-size: 12px; font-weight: 500; word-break: break-word; line-height: 1.4; }

.text-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.text-sev-low { color: var(--good); }
.text-sev-medium { color: var(--warn); }
.text-sev-high { color: var(--bad); }
.text-sev-critical { color: var(--crit); font-weight: 700; }
</style>