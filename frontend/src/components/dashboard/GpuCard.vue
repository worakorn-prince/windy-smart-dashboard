<script setup lang="ts">
import type { GpuInfo, GpuSnapshot } from '@/stores/metrics'
import { useMetricsStore, severityOf, SEVERITY_COLORS } from '@/stores/metrics'
import { computed } from 'vue'

const props = defineProps<{ gpu: GpuSnapshot | null }>()
const store = useMetricsStore()
const sensorMsg = computed(() => store.sensorStatus?.message ?? '')
const noLiveSensors = computed(() => {
  const gpus = props.gpu?.gpus ?? []
  if (!gpus.length) return false
  return gpus.every((g) => g.temperature_celsius == null && g.power_draw_watts == null)
})

const maxUsage = computed(() => {
  const gpus = props.gpu?.gpus ?? []
  const vals = gpus.map((g) => g.gpu_usage_percent ?? g.vram_usage_percent).filter((v): v is number => v != null)
  if (!vals.length) return null
  return Math.max(...vals)
})
const gpuSev = computed(() => severityOf('gpu', maxUsage.value))
const gpuSevColor = computed(() => SEVERITY_COLORS[gpuSev.value])

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

const vramPercent = (g: GpuInfo): string => {
  if (g.vram_usage_percent != null) return `${g.vram_usage_percent.toFixed(1)}%`
  if (g.vram_total_mb) return `${(((g.vram_used_mb ?? 0) / g.vram_total_mb) * 100).toFixed(1)}%`
  return '—'
}

const clocksText = (g: GpuInfo): string => {
  const core = g.graphics_clock_mhz
  const mem = g.memory_clock_mhz
  if (core == null && mem == null) return '—'
  const fmt = (v: number | null | undefined) => (v == null ? '—' : String(v))
  return `${fmt(core)} / ${fmt(mem)} MHz`
}

const vramFreeGb = (g: GpuInfo): string => (g.vram_free_mb == null ? '—' : `${(g.vram_free_mb / 1024).toFixed(1)} GB`)
</script>

<template>
  <div class="card gpu-card">
    <div class="card-head">
      <span class="card-icon" aria-hidden="true">◈</span>
      <h3>GPU</h3>
    </div>
    <div v-if="gpu && gpu.gpus.length > 0">
      <div class="hero" data-testid="gpu-hero" :data-severity="gpuSev">
        <span class="hero-value" data-testid="gpu-hero-value" :style="{ color: gpuSevColor }">{{ maxUsage != null ? maxUsage.toFixed(1) + '%' : 'N/A' }}</span>
        <span class="hero-label">Max GPU Usage</span>
      </div>
      <div v-for="(g, i) in gpu.gpus" :key="i" class="gpu-block">
        <div class="gpu-header">
          <span class="gpu-name" v-auto-tip>{{ vendorIcon(g.vendor) }} {{ g.name }}</span>
          <span class="badge">{{ g.vendor }}</span>
        </div>

        <!-- Real-time metrics (NVIDIA via nvidia-smi) -->
        <div v-if="g.gpu_usage_percent != null" class="usage-section">
          <div class="row small">
            <span class="label">Core Usage</span>
            <span class="value"><strong>{{ g.gpu_usage_percent }}%</strong></span>
          </div>
          <div class="progress">
            <div :style="{ width: (g.gpu_usage_percent || 0) + '%' }"></div>
          </div>
          <div class="row small" v-if="g.vram_total_mb">
            <span class="label">VRAM</span>
            <span class="value">
              {{ g.vram_used_mb }} / {{ g.vram_total_mb }} MB
              <span class="vram-pct" data-testid="gpu-vram-pct">{{ vramPercent(g) }}</span>
            </span>
          </div>
          <div class="progress" v-if="g.vram_total_mb">
            <div :style="{ width: (g.vram_usage_percent ?? ((g.vram_used_mb || 0) / g.vram_total_mb * 100)) + '%', background: 'var(--info)' }"></div>
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
          <div class="info-row" v-if="g.vram_free_mb != null">
            <span class="label">VRAM Free</span>
            <span class="value">{{ vramFreeGb(g) }}</span>
          </div>
          <div class="info-row">
            <span class="label">Clocks</span>
            <span class="value" data-testid="gpu-clocks">{{ clocksText(g) }}</span>
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
.gpu-card { min-width: 0; }
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.card-icon {
  font-size: 16px;
  line-height: 1;
  color: var(--accent-3);
}
.card-head h3 {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-dim);
}
.hero {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 2px 0 12px;
}
.hero-value {
  font-size: 38px;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.hero-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
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
.info-row .label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.3px; }
.info-row .value { font-size: 12px; font-weight: 500; word-break: break-word; line-height: 1.4; }

.text-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.vram-pct { color: var(--muted); margin-left: 4px; font-variant-numeric: tabular-nums; }

.text-sev-low { color: var(--good); }
.text-sev-medium { color: var(--warn); }
.text-sev-high { color: var(--bad); }
.text-sev-critical { color: var(--crit); font-weight: 700; }
</style>