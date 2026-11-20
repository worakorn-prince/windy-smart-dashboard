<script setup lang="ts">
import { onMounted, computed } from 'vue';
import { useInternetStore } from '@/stores/internet';
import InternetOverview from './InternetOverview.vue';
import QualitySummary from './QualitySummary.vue';
import NetworkInterfacesList from './NetworkInterfacesList.vue';

const store = useInternetStore();

async function loadData(): Promise<void> {
  await store.loadAll();
}

onMounted(() => {
  loadData();
  // Refresh every 30 seconds
  const interval = setInterval(loadData, 30000);
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
        <h2>คุณภาพการเชื่อมต่อ</h2>
        <div class="quality-grid">
          <QualitySummary target-id="gateway" data-testid="quality-gateway" />
          <QualitySummary target-id="primary" data-testid="quality-primary" />
          <QualitySummary target-id="secondary" data-testid="quality-secondary" />
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

.quality-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
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