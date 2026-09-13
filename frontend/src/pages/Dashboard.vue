<script setup lang="ts">
import { onMounted } from 'vue'
import { useMetricsStore } from '@/stores/metrics'
import HealthStrip from '@/components/dashboard/HealthStrip.vue'
import AlertsCard from '@/components/dashboard/AlertsCard.vue'
import CpuCard from '@/components/dashboard/CpuCard.vue'
import RamCard from '@/components/dashboard/RamCard.vue'
import GpuCard from '@/components/dashboard/GpuCard.vue'
import PowerCard from '@/components/dashboard/PowerCard.vue'
import DiskCard from '@/components/dashboard/DiskCard.vue'
import HistoryCard from '@/components/dashboard/HistoryCard.vue'
import NetworkCard from '@/components/dashboard/NetworkCard.vue'
import AdaptersCard from '@/components/dashboard/AdaptersCard.vue'
import ProcessesCard from '@/components/dashboard/ProcessesCard.vue'
import SystemCard from '@/components/dashboard/SystemCard.vue'
import SpeedtestCard from '@/components/dashboard/SpeedtestCard.vue'

const store = useMetricsStore()

onMounted(() => {
  store.connect()
})
</script>

<template>
  <div class="dashboard">
    <HealthStrip />
    <AlertsCard />
    <div class="grid primary-zone" data-testid="primary-zone">
      <CpuCard :cpu="store.cpu" :history="store.cpuHistory" />
      <RamCard :ram="store.ram" :history="store.ramHistory" />
      <GpuCard :gpu="store.gpu" />
    </div>
    <div class="grid secondary-zone" data-testid="secondary-zone">
      <PowerCard />
      <DiskCard :disk="store.disk" />
      <NetworkCard :network="store.network" :ping="store.ping" />
      <SystemCard :system="store.system" />
      <SpeedtestCard />
    </div>
    <div class="grid wide">
      <HistoryCard />
      <ProcessesCard :processes="store.processes" />
      <AdaptersCard :adapters="store.network?.adapters" />
    </div>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }
.grid.wide { grid-template-columns: 1fr; }
@media (min-width: 1400px) {
  .grid { width: 100%; max-width: none; }
}
@media (max-width: 720px) {
  .grid { grid-template-columns: 1fr; }
  .cpu-card { grid-column: span 1; }
}
</style>
