<script setup lang="ts">
import type { DiskSnapshot } from '@/stores/metrics'
import { formatBytes, formatRate } from '@/composables/format'

defineProps<{ disk: DiskSnapshot | null }>()

const color = (v: number) => (v > 90 ? 'var(--bad)' : v > 75 ? 'var(--warn)' : 'var(--accent)')
const healthColor = (h: string) => {
  if (!h || h === 'Unknown') return 'var(--muted)'
  if (h === 'Good') return 'var(--good)'
  if (h === 'Warning') return 'var(--warn)'
  if (h === 'Critical') return 'var(--bad)'
  return 'var(--muted)'
}
const typeIcon = (t: string) => {
  if (t.includes('NVMe')) return '⚡'
  if (t.includes('SSD')) return '💾'
  if (t.includes('HDD')) return '💿'
  return '💽'
}

function tempClass(v: number) {
  if (v >= 55) return 'text-sev-critical'
  if (v >= 45) return 'text-sev-high'
  if (v >= 35) return 'text-sev-medium'
  return 'text-sev-low'
}

function badgeTextColor(h: string) {
  if (h === 'Warning') return '#1a1a1a'
  return '#fff'
}
</script>

<template>
  <div class="card">
    <h3>Storage</h3>
    <div v-if="disk">
      <!-- Partitions -->
      <div class="section" v-if="disk.partitions.length > 0">
        <h4>Partitions</h4>
        <table>
          <thead>
            <tr>
              <th>Mount</th>
              <th>Filesystem</th>
              <th>Used / Total</th>
              <th>Usage</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in disk.partitions" :key="p.mountpoint">
              <td class="value">{{ p.mountpoint }}</td>
              <td class="muted small">{{ p.fstype }}</td>
              <td class="value">{{ (p.used / 1024**3).toFixed(1) }} GB / {{ (p.total / 1024**3).toFixed(1) }} GB</td>
              <td>
                <div class="progress">
                  <div :style="{ width: p.percent + '%', background: color(p.percent) }"></div>
                </div>
                <span class="small" :style="{ color: color(p.percent) }">{{ p.percent.toFixed(0) }}%</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- I/O Rates -->
      <div class="section">
        <h4>I/O Activity</h4>
        <div class="info-grid">
          <div class="info-row">
            <span class="label">Read Speed</span>
            <span class="value">{{ formatRate(disk.io.read_bytes_per_sec) }}</span>
          </div>
          <div class="info-row">
            <span class="label">Write Speed</span>
            <span class="value">{{ formatRate(disk.io.write_bytes_per_sec) }}</span>
          </div>
        </div>
      </div>

      <!-- Physical Drives -->
      <div class="section" v-if="disk.details && disk.details.length > 0">
        <h4>Physical Drives</h4>
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>Type</th>
              <th>Capacity</th>
              <th>Interface</th>
              <th>Health</th>
              <th>Temp</th>
              <th>Serial</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in disk.details" :key="d.model">
              <td class="value text-truncate" :title="d.model">{{ typeIcon(d.type) }} {{ d.model }}</td>
              <td class="value">{{ d.type }}</td>
              <td class="value">{{ d.capacity_gb }} GB</td>
              <td class="muted small">{{ d.interface }}</td>
              <td>
                <span class="badge" :style="{ background: healthColor(d.smart_health), color: badgeTextColor(d.smart_health) }">{{ d.smart_health }}</span>
              </td>
              <td class="value" v-if="disk.temperatures && disk.temperatures[d.model] !== undefined">
                <span :class="tempClass(disk.temperatures[d.model])">{{ disk.temperatures[d.model] }}°C</span>
              </td>
              <td class="muted small text-truncate" :title="d.serial">{{ d.serial }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- SMART Details (expandable) -->
      <div class="section" v-if="disk.details && disk.details.length > 0">
        <h4>SMART Details</h4>
        <div v-for="d in disk.details" :key="d.model" class="smart-detail">
          <div class="smart-header">
            <span class="label">{{ d.model }}</span>
            <span class="value">Firmware: {{ d.firmware }}</span>
          </div>
          <div v-if="d.smart_raw && Object.keys(d.smart_raw).length > 0" class="smart-attrs">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Attribute</th>
                  <th>Value</th>
                  <th>Worst</th>
                  <th>Thresh</th>
                  <th>Raw</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(attr, name) in d.smart_raw" :key="name">
                  <td class="value">{{ attr.id }}</td>
                  <td class="value">{{ name }}</td>
                  <td class="value">{{ attr.value }}</td>
                  <td class="value">{{ attr.worst }}</td>
                  <td class="value">{{ attr.thresh }}</td>
                  <td class="value monospace">{{ attr.raw }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="muted small">SMART attributes not available (requires smartctl or admin)</p>
        </div>
      </div>

      <!-- Temperatures -->
      <div class="section" v-if="disk.temperatures && Object.keys(disk.temperatures).length > 0">
        <h4>Drive Temperatures</h4>
        <div class="temp-grid">
          <div v-for="(temp, name) in disk.temperatures" :key="name" class="temp-item">
            <span class="temp-label" v-auto-tip>{{ name }}</span>
            <span class="temp-value" :class="tempClass(temp)">{{ temp }}°C</span>
          </div>
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

table { width: 100%; border-collapse: collapse; font-size: 11px; table-layout: fixed; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--border); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
th { color: var(--muted); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
td { font-size: 11px; }
.monospace { font-family: 'JetBrains Mono', monospace; font-size: 10px; }

.smart-detail { margin-bottom: 16px; background: var(--panel-2); border-radius: 8px; padding: 12px; }
.smart-header { display: flex; justify-content: space-between; margin-bottom: 8px; font-weight: 600; }
.smart-attrs table { font-size: 10px; }
.smart-attrs th, .smart-attrs td { padding: 4px 6px; font-size: 10px; }

.temp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 8px; margin-top: 8px; }
.temp-item { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px; background: var(--panel-2); border-radius: 6px; min-width: 0; }
.temp-label { font-size: 9px; color: var(--muted); max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.temp-value { font-size: 14px; font-weight: 700; }

.text-sev-low { color: var(--good); }
.text-sev-medium { color: var(--warn); }
.text-sev-high { color: var(--bad); }
.text-sev-critical { color: var(--crit); font-weight: 700; }
</style>