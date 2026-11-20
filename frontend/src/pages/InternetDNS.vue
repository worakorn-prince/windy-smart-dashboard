<script setup lang="ts">
import { onMounted, computed, ref, watch } from 'vue'
import { useInternetStore } from '@/stores/internet'
import DnsResolverCard from '@/components/internet/DnsResolverCard.vue'
import DnsHistoryChart from '@/components/internet/DnsHistoryChart.vue'
import DnsComparison from '@/components/internet/DnsComparison.vue'

const store = useInternetStore()

const activeRange = ref<'5m' | '1h' | '6h' | '24h' | '7d' | '30d'>('1h')
const showCompareModal = ref(false)
const compareHostname = ref('google.com')
const compareRecordType = ref<'A' | 'AAAA' | 'CNAME' | 'TXT' | 'MX'>('A')

async function loadData(): Promise<void> {
  await Promise.all([
    store.loadDns(),
    store.loadDnsHistory(activeRange.value),
  ])
}

async function loadCompare() {
  if (!compareHostname.value.trim()) return
  await store.loadDnsCompare(compareHostname.value.trim(), compareRecordType.value)
  showCompareModal.value = true
}

function openCompareModal() {
  showCompareModal.value = true
}

async function runCompare() {
  await loadCompare()
}

onMounted(() => {
  loadData()
  const interval = setInterval(() => {
    loadData()
  }, 30000)
  return () => clearInterval(interval)
})

watch(activeRange, () => {
  store.loadDnsHistory(activeRange.value)
})

const configuredResolvers = computed(() => store.dns?.configured_resolvers ?? [])
const resolverHealth = computed(() => store.dns?.resolver_health ?? [])

const healthyCount = computed(() => resolverHealth.value.filter(r => r.status === 'ok').length)
const degradedCount = computed(() => resolverHealth.value.filter(r => r.status === 'degraded').length)
const downCount = computed(() => resolverHealth.value.filter(r => r.status === 'down').length)

function formatTimeAgo(ts: number | null): string {
  if (!ts) return '—'
  const diff = (Date.now() - ts * 1000) / 1000
  if (diff < 60) return `${Math.floor(diff)} วินาทีที่แล้ว`
  if (diff < 3600) return `${Math.floor(diff / 60)} นาทีที่แล้ว`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ชั่วโมงที่แล้ว`
  return `${Math.floor(diff / 86400)} วันที่แล้ว`
}

function setRange(r: '5m' | '1h' | '6h' | '24h' | '7d' | '30d') {
  activeRange.value = r
}
</script>

<template>
  <div class="internet-dns-page" data-testid="internet-dns-page">
    <header class="page-header">
      <h1>DNS Insights</h1>
      <p class="page-subtitle">ตรวจสอบสถานะ DNS Resolver, เลตันซี, และเปรียบเทียบประสิทธิภาพ</p>
    </header>

    <div v-if="store.loading && !store.dns" class="loading-state" data-testid="dns-loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <span>กำลังโหลดข้อมูล DNS...</span>
    </div>

    <div v-else-if="store.error" class="error-state" data-testid="dns-error-state">
      <p class="error-message">{{ store.error }}</p>
      <button @click="loadData" class="retry-btn">ลองใหม่</button>
    </div>

    <div v-else class="content-grid">
      <section class="overview-section" data-testid="dns-overview-section">
        <div class="section-header">
          <h2>DNS Resolver Status</h2>
          <div class="status-summary">
            <span class="status-count ok" :data-testid="`dns-count-ok`">{{ healthyCount }} OK</span>
            <span class="status-count degraded" :data-testid="`dns-count-degraded`">{{ degradedCount }} Degraded</span>
            <span class="status-count down" :data-testid="`dns-count-down`">{{ downCount }} Down</span>
          </div>
        </div>

        <div v-if="resolverHealth.length" class="resolver-cards" data-testid="dns-resolver-cards">
          <DnsResolverCard
            v-for="resolver in resolverHealth"
            :key="resolver.resolver"
            :resolver="resolver"
          />
        </div>

        <div v-else class="empty-state" data-testid="dns-empty-resolvers">
          <p>ไม่พบ DNS Resolver ที่ตั้งค่าไว้</p>
        </div>
      </section>

      <section class="history-section" data-testid="dns-history-section">
        <div class="section-header">
          <h2>DNS Latency History</h2>
          <div class="range-selector" data-testid="dns-range-selector">
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

        <div class="charts-grid">
          <DnsHistoryChart :range="activeRange" :height="220" data-testid="dns-history-all" />
          <DnsHistoryChart
            v-for="resolver in configuredResolvers"
            :key="resolver"
            :range="activeRange"
            :height="220"
            :resolver="resolver"
          />
        </div>
      </section>

      <section class="compare-section" data-testid="dns-compare-section">
        <div class="section-header">
          <h2>DNS Comparison</h2>
        </div>
        <div class="compare-form">
          <div class="form-row">
            <label for="compare-hostname">Hostname</label>
            <input
              id="compare-hostname"
              type="text"
              v-model="compareHostname"
              placeholder="google.com"
              @keyup.enter="runCompare"
              data-testid="dns-compare-hostname"
            />
          </div>
          <div class="form-row">
            <label for="compare-record-type">Record Type</label>
            <select
              id="compare-record-type"
              v-model="compareRecordType"
              data-testid="dns-compare-record-type"
            >
              <option value="A">A</option>
              <option value="AAAA">AAAA</option>
              <option value="CNAME">CNAME</option>
              <option value="TXT">TXT</option>
              <option value="MX">MX</option>
            </select>
          </div>
          <button type="button" class="btn-primary" @click="runCompare" :disabled="store.loading" data-testid="dns-compare-run">
            <span v-if="store.loading" class="spinner-sm" aria-hidden="true"></span>
            {{ store.loading ? 'Comparing...' : 'เปรียบเทียบ' }}
          </button>
        </div>
      </section>
    </div>

    <DnsComparison
      v-model="showCompareModal"
      :comparison="store.dnsCompare?.comparison ?? []"
      :hostname="compareHostname"
      :record-type="compareRecordType"
      data-testid="dns-comparison-modal"
    />
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

.status-summary {
  display: flex;
  gap: 8px;
}

.status-count {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  font-family: var(--font-mono, ui-monospace, monospace);
}

.status-count.ok { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.status-count.degraded { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.status-count.down { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

.resolver-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.charts-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}

@media (min-width: 768px) {
  .charts-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.compare-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
}

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.form-row label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-dim);
  min-width: 100px;
}

.form-row input,
.form-row select {
  flex: 1;
  min-width: 200px;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-ctl);
  color: var(--text);
  font-size: 13px;
  font-family: var(--font-mono, ui-monospace, monospace);
}

.form-row input:focus,
.form-row select:focus {
  outline: none;
  border-color: var(--accent);
}

.btn-primary {
  align-self: flex-start;
  background: var(--accent);
  color: var(--on-accent);
  border: none;
  padding: 10px 20px;
  border-radius: var(--radius-btn);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s ease;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-strong);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid var(--on-accent);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
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
</style>