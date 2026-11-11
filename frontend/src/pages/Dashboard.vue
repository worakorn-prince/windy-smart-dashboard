<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useMetricsStore, severityOf, type SeverityLevel } from '@/stores/metrics'
import StatRow from '@/components/dashboard/StatRow.vue'
import AlertsCard from '@/components/dashboard/AlertsCard.vue'
import AlertRulesCard from '@/components/dashboard/AlertRulesCard.vue'
import CpuCard from '@/components/dashboard/CpuCard.vue'
import RamCard from '@/components/dashboard/RamCard.vue'
import GpuCard from '@/components/dashboard/GpuCard.vue'
import PowerCard from '@/components/dashboard/PowerCard.vue'
import BatteryCard from '@/components/dashboard/BatteryCard.vue'
import DiskCard from '@/components/dashboard/DiskCard.vue'
import HistoryCard from '@/components/dashboard/HistoryCard.vue'
import NetworkCard from '@/components/dashboard/NetworkCard.vue'
import AdaptersCard from '@/components/dashboard/AdaptersCard.vue'
import ProcessesCard from '@/components/dashboard/ProcessesCard.vue'
import ProcessDetailPanel from '@/components/dashboard/ProcessDetailPanel.vue'
import SystemCard from '@/components/dashboard/SystemCard.vue'
import SpeedtestCard from '@/components/dashboard/SpeedtestCard.vue'
import {
  CARD_DEFS,
  canMoveCard,
  loadLayout,
  moveCard,
  resetLayout,
  saveLayout,
  toggleHidden,
  zoneOf,
} from '@/composables/useLayout'
import type { CardDef, CardZone, LayoutState } from '@/composables/useLayout'

const store = useMetricsStore()
const selectedPid = ref<number | null>(null)

const COMPONENTS: Record<string, Component> = {
  alerts: AlertsCard,
  'alert-rules': AlertRulesCard,
  cpu: CpuCard,
  ram: RamCard,
  gpu: GpuCard,
  power: PowerCard,
  battery: BatteryCard,
  disk: DiskCard,
  network: NetworkCard,
  system: SystemCard,
  speedtest: SpeedtestCard,
  history: HistoryCard,
  processes: ProcessesCard,
  adapters: AdaptersCard,
}

const CARD_MAP: Record<string, CardDef> = CARD_DEFS.reduce<Record<string, CardDef>>((acc, def) => {
  acc[def.id] = def
  return acc
}, {})

const layout = ref<LayoutState>(loadLayout())
const showLayoutPanel = ref(false)

const hasBattery = computed(() => Boolean(store.system?.battery))

const hostname = computed(() => store.system?.hostname || 'DESKTOP')

const maxTemp = computed<number | null>(() => {
  const candidates: number[] = []
  const cpuTemp = store.cpu?.temperature_celsius
  if (cpuTemp?.primary !== null && cpuTemp?.primary !== undefined) candidates.push(cpuTemp.primary)
  if (cpuTemp?.max !== null && cpuTemp?.max !== undefined) candidates.push(cpuTemp.max)
  for (const g of store.gpu?.gpus ?? []) {
    if (g.temperature_celsius !== null && g.temperature_celsius !== undefined) {
      candidates.push(g.temperature_celsius)
    }
  }
  for (const t of store.ram?.temperature_celsius?.temps ?? []) {
    if (t.value !== null && t.value !== undefined) candidates.push(t.value)
  }
  if (!candidates.length) return null
  return Math.max(...candidates)
})

const SEVERITY_RANK: Record<SeverityLevel, number> = { ok: 0, warn: 1, crit: 2 }

const statusLevel = computed<SeverityLevel>(() => {
  const levels: SeverityLevel[] = [
    severityOf('cpu', store.cpu?.overall ?? null),
    severityOf('ram', store.ram?.percent ?? null),
    severityOf('temp', maxTemp.value),
  ]
  return levels.reduce<SeverityLevel>(
    (worst, level) => (SEVERITY_RANK[level] > SEVERITY_RANK[worst] ? level : worst),
    'ok',
  )
})

const statusText = computed(() => {
  if (statusLevel.value === 'crit') return 'วิกฤต'
  if (statusLevel.value === 'warn') return 'ควรเฝ้าระวัง'
  return 'ปกติ'
})

function fmtTemp(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}°C`
}

const sideFacts = computed(() => {
  const sys = store.system
  const ram = store.ram
  const partitions = store.disk?.partitions ?? []
  const diskTotal = partitions.reduce((sum, p) => sum + (p.total ?? 0), 0)
  const diskUsed = partitions.reduce((sum, p) => sum + (p.used ?? 0), 0)
  const gpuTemps = (store.gpu?.gpus ?? [])
    .map((g) => g.temperature_celsius)
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))

  return [
    { label: 'ระบบปฏิบัติการ', value: sys?.os_name || sys?.os || '—' },
    { label: 'เวลาทำงาน', value: sys?.uptime || '—' },
    { label: 'อุณหภูมิ CPU', value: fmtTemp(store.cpu?.temperature_celsius?.primary ?? null) },
    { label: 'อุณหภูมิ GPU', value: fmtTemp(gpuTemps.length ? Math.max(...gpuTemps) : null) },
    {
      label: 'หน่วยความจำ',
      value: ram ? `${ram.used.toFixed(1)} / ${ram.total.toFixed(0)} GB` : '—',
    },
    {
      label: 'พื้นที่จัดเก็บ',
      value: partitions.length ? `${diskUsed.toFixed(0)} / ${diskTotal.toFixed(0)} GB` : '—',
    },
    { label: 'การแจ้งเตือนค้าง', value: `${store.alerts.length} รายการ` },
  ]
})

watch(
  layout,
  (state) => {
    saveLayout(state)
  },
  { deep: true },
)

function zoneCards(zone: CardZone): string[] {
  return layout.value.order.filter((id) => zoneOf(id) === zone && !layout.value.hidden.includes(id))
}

function isHidden(id: string): boolean {
  return layout.value.hidden.includes(id)
}

function canMove(id: string, dir: -1 | 1): boolean {
  return canMoveCard(layout.value, id, dir)
}

function onMove(id: string, dir: -1 | 1) {
  layout.value = moveCard(layout.value, id, dir)
}

function onToggleHidden(id: string) {
  layout.value = toggleHidden(layout.value, id)
}

function onReset() {
  layout.value = resetLayout()
}

function propsFor(id: string): Record<string, unknown> {
  switch (id) {
    case 'cpu':
      return { cpu: store.cpu, history: store.cpuHistory }
    case 'ram':
      return { ram: store.ram, history: store.ramHistory }
    case 'gpu':
      return { gpu: store.gpu }
    case 'battery':
      return { battery: store.system?.battery ?? null }
    case 'disk':
      return { disk: store.disk }
    case 'network':
      return { network: store.network, ping: store.ping }
    case 'system':
      return { system: store.system }
    case 'processes':
      return { processes: store.processes, selectedPid: selectedPid.value }
    case 'adapters':
      return { adapters: store.network?.adapters }
    default:
      return {}
  }
}

function handlersFor(id: string): Record<string, (...args: any[]) => void> {
  if (id === 'processes') {
    return {
      select: (pid: number) => {
        selectedPid.value = pid
      },
    }
  }
  return {}
}

onMounted(() => {
  store.connect()
})
</script>

<template>
  <div class="dashboard">
    <header class="page-head" data-testid="dashboard-head">
      <div class="head-left">
        <p class="breadcrumb">WORKSTATION / {{ hostname }}</p>
        <h1>ภาพรวมประสิทธิภาพระบบ</h1>
        <p class="subtitle">ติดตามการใช้ทรัพยากรแบบเรียลไทม์</p>
      </div>

      <div class="head-right">
        <span class="status-pill" :class="`sev-${statusLevel}`" data-testid="dashboard-status">
          <span class="dot" aria-hidden="true"></span>
          {{ statusText }}
        </span>

        <button type="button" class="btn-ghost" data-testid="dashboard-export">ส่งออกรายงาน ▾</button>

        <div class="layout-toolbar" data-testid="layout-toolbar">
          <button
            type="button"
            class="layout-btn"
            data-testid="layout-toggle"
            :aria-expanded="showLayoutPanel"
            @click="showLayoutPanel = !showLayoutPanel"
          >
            Layout
          </button>
          <button type="button" class="layout-btn" data-testid="layout-reset" @click="onReset">Reset</button>
          <div v-if="showLayoutPanel" class="layout-panel" data-testid="layout-panel">
            <div v-for="id in layout.order" :key="id" class="layout-row" :data-testid="`layout-row-${id}`">
              <span class="layout-title">{{ CARD_MAP[id].title }}</span>
              <span class="layout-zone">{{ CARD_MAP[id].zone }}</span>
              <button
                type="button"
                class="layout-btn icon"
                :data-testid="`layout-up-${id}`"
                :disabled="!canMove(id, -1)"
                aria-label="Move up"
                @click="onMove(id, -1)"
              >
                ↑
              </button>
              <button
                type="button"
                class="layout-btn icon"
                :data-testid="`layout-down-${id}`"
                :disabled="!canMove(id, 1)"
                aria-label="Move down"
                @click="onMove(id, 1)"
              >
                ↓
              </button>
              <button
                type="button"
                class="layout-btn"
                :data-testid="`layout-hide-${id}`"
                @click="onToggleHidden(id)"
              >
                {{ isHidden(id) ? 'Show' : 'Hide' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>

    <StatRow />

    <section class="dash-split">
      <div class="dash-main">
        <div class="grid">
          <component
            :is="COMPONENTS[id]"
            v-for="id in zoneCards('alerts')"
            :key="id"
            :data-card-id="id"
            v-bind="propsFor(id)"
            v-on="handlersFor(id)"
          />
        </div>
        <div class="grid primary-zone" data-testid="primary-zone">
          <component
            :is="COMPONENTS[id]"
            v-for="id in zoneCards('primary')"
            :key="id"
            :data-card-id="id"
            v-bind="propsFor(id)"
            v-on="handlersFor(id)"
          />
        </div>
        <div class="grid secondary-zone" data-testid="secondary-zone">
          <template v-for="id in zoneCards('secondary')" :key="id">
            <component
              :is="COMPONENTS[id]"
              v-if="id !== 'battery' || hasBattery"
              :data-card-id="id"
              v-bind="propsFor(id)"
              v-on="handlersFor(id)"
            />
          </template>
        </div>
        <div class="grid wide">
          <component
            :is="COMPONENTS[id]"
            v-for="id in zoneCards('wide')"
            :key="id"
            :data-card-id="id"
            v-bind="propsFor(id)"
            v-on="handlersFor(id)"
          />
        </div>
      </div>

      <aside class="dash-side" data-testid="dashboard-side">
        <section class="card side-card">
          <h3 class="side-title">ภาพรวมระบบ</h3>
          <div class="side-list">
            <div v-for="fact in sideFacts" :key="fact.label" class="side-row">
              <span class="side-label">{{ fact.label }}</span>
              <span class="side-value">{{ fact.value }}</span>
            </div>
          </div>
        </section>
      </aside>
    </section>

    <ProcessDetailPanel :pid="selectedPid" @close="selectedPid = null" />
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  flex-wrap: wrap;
}
.head-left { min-width: 0; }
.breadcrumb {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0;
}
.page-head h1 {
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
  margin: 4px 0;
}
.subtitle {
  font-size: 13px;
  color: var(--muted);
  margin: 0;
}
.head-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  background: var(--panel);
  font-size: 12px;
  color: var(--text-dim);
  white-space: nowrap;
}
.status-pill .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--good);
  flex: none;
}
.status-pill.sev-warn .dot { background: var(--warn); }
.status-pill.sev-crit .dot { background: var(--bad); }
.btn-ghost {
  background: var(--panel-2);
  color: var(--text-dim);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-ctl);
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.btn-ghost:hover {
  border-color: var(--accent);
  color: var(--text);
}

.dash-split {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.dash-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.dash-side {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.side-card { padding: 16px; }
.side-title {
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-dim);
}
.side-list { display: flex; flex-direction: column; gap: 8px; }
.side-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}
.side-label { color: var(--muted); flex: none; }
.side-value {
  color: var(--text);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: right;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.grid.wide { grid-template-columns: 1fr; }
.layout-toolbar { position: relative; display: flex; gap: 8px; align-items: center; }
.layout-btn {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--radius-ctl);
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
}
.layout-btn:hover:not(:disabled) { background: var(--panel-2); }
.layout-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.layout-btn.icon { padding: 4px 9px; line-height: 1; }
.layout-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 40;
  width: 320px;
  max-height: 60vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--panel);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-card);
  padding: 12px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
}
.layout-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.layout-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.layout-zone {
  color: var(--muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 72px;
}
@media (min-width: 1400px) {
  .grid { width: 100%; max-width: none; }
}
@media (max-width: 1200px) {
  .dash-split { flex-direction: column; }
  .dash-side { width: 100%; }
}
@media (max-width: 720px) {
  .grid { grid-template-columns: 1fr; }
  .cpu-card { grid-column: span 1; }
  .page-head h1 { font-size: 21px; }
  .head-right { justify-content: flex-start; }
}
</style>
