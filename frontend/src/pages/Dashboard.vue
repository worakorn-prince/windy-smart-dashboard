<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useMetricsStore } from '@/stores/metrics'
import HealthStrip from '@/components/dashboard/HealthStrip.vue'
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
    <HealthStrip />
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
    <ProcessDetailPanel :pid="selectedPid" @close="selectedPid = null" />
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }
.grid.wide { grid-template-columns: 1fr; }
.layout-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; }
.layout-btn {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  cursor: pointer;
}
.layout-btn:hover:not(:disabled) { background: var(--panel-2); }
.layout-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.layout-btn.icon { padding: 4px 9px; line-height: 1; }
.layout-panel {
  flex-basis: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
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
@media (max-width: 720px) {
  .grid { grid-template-columns: 1fr; }
  .cpu-card { grid-column: span 1; }
}
</style>
