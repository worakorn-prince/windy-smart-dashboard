<script setup lang="ts">
import { onMounted, computed, ref } from 'vue';
import { useInternetStore } from '@/stores/internet';
import InternetOverview from './InternetOverview.vue';
import QualitySummary from './QualitySummary.vue';
import QualityStatus from './QualityStatus.vue';
import LatencyChart from './LatencyChart.vue';
import JitterChart from './JitterChart.vue';
import PacketLossChart from './PacketLossChart.vue';
import NetworkInterfacesList from './NetworkInterfacesList.vue';

const store = useInternetStore();

const activeRange = ref<'5m' | '1h' | '6h' | '24h' | '7d' | '30d'>('1h')

async function loadData(): Promise<void> {
  await store.loadAll();
  await store.loadQualityStatus(activeRange.value);
}

async function loadQualityHistory() {
  await Promise.all([
    store.loadQualityHistory(activeRange.value, 'gateway', 60),
    store.loadQualityHistory(activeRange.value, 'primary', 60),
    store.loadQualityHistory(activeRange.value, 'secondary', 60),
  ]);
}

onMounted(() => {
  loadData();
  loadQualityHistory();
  // Refresh every 30 seconds
  const interval = setInterval(() => {
    loadData();
    loadQualityHistory();
  }, 30000);
  return () => clearInterval(interval);
});

const interfaces = computed(() => store.interfaces?.interfaces ?? []);

function formatRate(bytesPerSec: number): string {
  if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`;
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
  return `${(bytesPerSec / 1024 / 1024).toFixed(2)} MB/s`;
}

function getStatusClass(status: string): string {
  return status === 'up' ? 'status-up' : status === 'down' ? 'status-down' : 'status-unknown';
}

function setRange(r: '5m' | '1h' | '6h' | '24h' | '7d' | '30d') {
  activeRange.value = r;
  loadQualityHistory();
  store.loadQualityStatus(r);
}
</script>

<template>
  <div class="internet-insights-page" data-testid="internet-insights-page">
    <header class="page-header">
      <h1>Internet Insights</h1>
      <p class="page-subtitle">ภาพรวมคุณภาพการเชื่อมต่ออินเทอร์เน็ตและอินเทอร์เฟซเครือข่าย</p>
    </header>

    <div v-if="store.loading" class="loading-state" data-testid="loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <span>กำลังโหลดข้อมูล...</span>
    </div>

    <div v-else-if="store.error" class="error-state" data-testid="error-state">
      <p class="error-message">{{ store.error }}</p>
      <button @click="loadData" class="retry-btn">ลองใหม่</button>
    </div>

    <div v-else class="content-grid">
      <section class="main-section" data-testid="overview-section">
        <InternetOverview />
      </section>

      <section class="quality-section" data-testid="quality-section">
        <div class="section-header">
          <h2>คุณภาพการเชื่อมต่อ</h2>
          <div class="range-selector" data-testid="quality-range-selector">
            <button
              v-for="r in ['5m', '1h', '6h', '24h', '7d', '30d']"
              :key="r"
              class="range-btn"
              :class="{ active: activeRange === r }"
              @click="setRange(r as any)"
            >
              {{ r === '5m' ? '5 นาที' : r === '1h' ? '1 ชม.' : r === '6h' ? '6 ชม.' : r === '24h' ? '24 ชม.' : r === '7d' ? '7 วัน' : '30 วัน' }}
            </button>
          </div>
        </div>

        <QualityStatus :range="activeRange" :auto-load="false" data-testid="quality-status" />

        <div class="quality-grid">
          <QualitySummary target-id="gateway" data-testid="quality-gateway" />
          <QualitySummary target-id="primary" data-testid="quality-primary" />
          <QualitySummary target-id="secondary" data-testid="quality-secondary" />
        </div>

        <div class="charts-grid" data-testid="quality-charts-grid">
          <div class="chart-column">
            <h3>Latency</h3>
            <LatencyChart target-id="gateway" :range="activeRange" ::height="180" data-testid="latency-gateway" />
            <LatencyChart target-id="primary" :range="activeRange" ::height="180" data-testid="latency-primary" />
            <LatencyChart target-id="secondary" :range="activeRange" ::height="180" data-testid="latency-secondary" />
          </div>
          <div class="chart-column">
            <h3>Jitter</h3>
            <JitterChart target-id="gateway" :range="activeRange" :height="180" data-testid="jitter-gateway" />
            <JitterChart target-id="primary" :range="activeRange" ::height="180" data-testid="jitter-primary" />
            <JitterChart target-id="secondary" :range="activeRange" ::height="180" data-testid="jitter-secondary" />
          </div>
          <div class="chart-column">
            <h3>Packet Loss</h3>
            <PacketLossChart target-id="gateway" :range="activeRange" ::height="180" data-testid="packet-loss-gateway" />
            <PacketLossChart target-id="primary" :range="activeRange" ::height="180" data-testid="packet-loss-primary" />
            <PacketLossChart target-id="secondary" :range="activeRange" ::height="180" data-testid="packet-loss-secondary" />
          </div>
        </div>
      </section>

      <section class="interfaces-section" data-testid="interfaces-section">
        <h2>อินเทอร์เฟซเครือข่าย</h2>
        <NetworkInterfacesList />
      </section>
    </div>
  </div>
</template>

<style scoped>
.content-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 20px;
}

@media (min-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.main-section {
  grid-column: 1 / -1;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.section-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}

.range-selector {
  display: flex;
  gap: 6px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px;
}

.range-btn {
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 12px;
  font-family: var(--font-mono, ui-monospace, monospace);
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.range-btn:hover { color: var(--text); border-color: var(--border-strong); }

.range-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 700;
}

.quality-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

@media (min-width: 768px) {
  .charts-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.chart-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chart-column h3 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
}

.page-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--muted);
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  gap: 16px;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-message {
  margin: 0;
  color: var(--bad);
  font-size: 14px;
}

.retry-btn {
  padding: 8px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: var(--radius-btn);
  font-weight: 600;
  cursor: pointer;
}

.retry-btn:hover {
  background: var(--accent-strong);
}

.section h2 {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}
</style>
