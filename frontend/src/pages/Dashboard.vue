<script setup lang="ts">
import { onMounted } from 'vue'
import { useMetricsStore } from '@/stores/metrics'
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
    <div class="grid">
      <CpuCard :cpu="store.cpu" :history="store.cpuHistory" />
      <RamCard :ram="store.ram" :history="store.ramHistory" />
      <GpuCard :gpu="store.gpu" />
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
</style>
