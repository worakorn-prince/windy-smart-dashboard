<script setup lang="ts">
import { onMounted, computed, ref, watch } from 'vue'
import { useInternetStore } from '@/stores/internet'
import RouteTable from '@/components/internet/RouteTable.vue'
import TracerouteView from '@/components/internet/TracerouteView.vue'
import RouteHistoryChart from '@/components/internet/RouteHistoryChart.vue'

const store = useInternetStore()

const activeRange = ref<'5m' | '1h' | '6h' | '24h' | '7d' | '30d'>('1h')
const tracerouteTarget = ref('8.8.8.8')
const tracerouteMaxHops = ref(30)
const tracerouteProtocol = ref<'icmp' | 'udp' | 'tcp'>('icmp')
const tracerouteLoading = ref(false)

async function loadData(): Promise<void> {
  await Promise.all([
    store.loadRoutes(),
    store.loadRoutesHistory(activeRange.value),
  ])
}

async function runTraceroute() {
  if (!tracerouteTarget.value.trim()) return
  tracerouteLoading.value = true
  try {
    await store.loadTraceroute(tracerouteTarget.value.trim(), tracerouteMaxHops.value, tracerouteProtocol.value)
  } finally {
    tracerouteLoading.value = false
  }
}

onMounted(() => {
  loadData()
  const interval = setInterval(() => {
    loadData()
  }, 30000)
  return () => clearInterval(interval)
})

watch(activeRange, () => {
  store.loadRoutesHistory(activeRange.value)
})

const routes = computed(() => store.routes?.routes ?? [])
const defaultGateway = computed(() => store.routes?.default_gateway ?? null)
const gatewayInterfaceIndex = computed(() => store.routes?.gateway_interface_index ?? null)

const tracerouteHops = computed(() => store.traceroute?.hops ?? [])
const tracerouteSessionId = computed(() => store.traceroute?.session_id ?? '')
const tracerouteTargetComputed = computed(() => store.traceroute?.target ?? tracerouteTarget.value)
const tracerouteMaxHopsComputed = computed(() => store.traceroute?.max_hops ?? tracerouteMaxHops.value)
const tracerouteProtocolComputed = computed(() => store.traceroute?.protocol ?? tracerouteProtocol.value)

function setRange(r: '5m' | '1h' | '6h' | '24h' | '7d' | '30d') {
  activeRange.value = r
}

function handleTracerouteRun() {
  runTraceroute()
}
</script>

<template>
  <div class="internet-routing-page" data-testid="internet-routing-page">
    <header class="page-header">
      <h1>Routing Insights</h1>
      <p class="page-subtitle">ตารางเส้นทาง (Route Table), Traceroute, และประวัติการเปลี่ยนแปลงเส้นทาง</p>
    </header>

    <div v-if="store.loading && !routes.length" class="loading-state" data-testid="routing-loading-state">
      <div class="spinner" aria-hidden="true"></div>
      <span>กำลังโหลดข้อมูล Routing...</span>
    </div>

    <div v-else-if="store.error" class="error-state" data-testid="routing-error-state">
      <p class="error-message">{{ store.error }}</p>
      <button @click="loadData" class="retry-btn">ลองใหม่</button>
    </div>

    <div v-else class="content-grid">
      <section class="routes-section" data-testid="routes-section">
        <div class="section-header">
          <h2>Route Table</h2>
        </div>

        <RouteTable
          :routes="routes"
          :default-gateway="defaultGateway"
          :gateway-interface-index="gatewayInterfaceIndex"
          data-testid="route-table"
        />
      </section>

      <section class="traceroute-section" data-testid="traceroute-section">
        <div class="section-header">
          <h2>Traceroute</h2>
        </div>

        <div class="traceroute-form" data-testid="traceroute-form">
          <div class="form-row">
            <label for="traceroute-target">Target</label>
            <input
              id="traceroute-target"
              type="text"
              v-model="tracerouteTarget"
              placeholder="8.8.8.8"
              @keyup.enter="runTraceroute"
              data-testid="traceroute-target-input"
            />
          </div>
          <div class="form-row">
            <label for="traceroute-max-hops">Max Hops</label>
            <input
              id="traceroute-max-hops"
              type="number"
              v-model.number="tracerouteMaxHops"
              min="1"
              max="64"
              data-testid="traceroute-max-hops-input"
            />
          </div>
          <div class="form-row">
            <label for="traceroute-protocol">Protocol</label>
            <select
              id="traceroute-protocol"
              v-model="tracerouteProtocol"
              data-testid="traceroute-protocol-select"
            >
              <option value="icmp">ICMP</option>
              <option value="udp">UDP</option>
              <option value="tcp">TCP</option>
            </select>
          </div>
          <button
            type="button"
            class="btn-primary"
            @click="runTraceroute"
            :disabled="tracerouteLoading"
            data-testid="traceroute-run-btn"
          >
            <span v-if="tracerouteLoading" class="spinner-sm" aria-hidden="true"></span>
            {{ tracerouteLoading ? 'Running...' : 'Run Traceroute' }}
          </button>
        </div>

        <TracerouteView
          :hops="tracerouteHops"
          :target="tracerouteTargetComputed"
          :max-hops="tracerouteMaxHopsComputed"
          :protocol="tracerouteProtocolComputed"
          :session-id="tracerouteSessionId"
          @run="handleTracerouteRun"
          data-testid="traceroute-view"
        />
      </section>

      <section class="history-section" data-testid="routing-history-section">
        <div class="section-header">
          <h2>Route History</h2>
          <div class="range-selector" data-testid="routing-range-selector">
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

        <RouteHistoryChart :range="activeRange" :height="300" data-testid="route-history-chart" />
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

  .routes-section {
    grid-column: 1 / -1;
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

.traceroute-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
  margin-bottom: 16px;
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
  cursor: pointer.
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
  padding: 3px.
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