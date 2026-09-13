<script setup lang="ts">
import { ref } from 'vue'
import { useMetricsStore } from '@/stores/metrics'

const collapsed = ref(false)
const store = useMetricsStore()
</script>

<template>
  <div class="card">
    <h3>Internet Speed Test <button data-testid="card-toggle" @click="collapsed = !collapsed">{{ collapsed ? '+' : '−' }}</button></h3>
    <div v-show="!collapsed">
    <div v-if="store.speedtest" class="result">
      <div v-if="store.speedtest.ok">
        <div class="row">
          <span class="label">↓ Download</span>
          <span class="value big">{{ store.speedtest.download_mbps }}</span>
          <span class="muted">Mbps</span>
        </div>
        <div class="row">
          <span class="label">↑ Upload</span>
          <span class="value big">{{ store.speedtest.upload_mbps }}</span>
          <span class="muted">Mbps</span>
        </div>
        <div class="row">
          <span class="label">Ping</span>
          <span class="value">{{ store.speedtest.ping_ms }} ms</span>
        </div>
        <div class="row small" v-if="store.speedtest.server">
          <span class="label">Server</span>
          <span class="value">{{ store.speedtest.server.sponsor || store.speedtest.server.name }}</span>
        </div>
      </div>
      <p v-else class="muted small">Failed: {{ store.speedtest.error }}</p>
    </div>
    <p v-else-if="store.speedtestRunning" class="muted small">
      Running… (uses ~20-30 MB of bandwidth)
    </p>
    <p v-else class="muted small">
      Uses the best-rated test server from speedtest.net. Each run consumes bandwidth.
    </p>
    <button class="primary" :disabled="store.speedtestRunning" @click="store.runSpeedtest()">
      {{ store.speedtestRunning ? 'Running…' : 'Run Speed Test' }}
    </button>
    </div>
  </div>
</template>

<style scoped>
.big { font-size: 20px; font-weight: 700; }
.result { margin-bottom: 12px; }
</style>
