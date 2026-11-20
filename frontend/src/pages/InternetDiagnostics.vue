<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useInternetStore } from '@/stores/internet'

const store = useInternetStore()

type DiagTool = 'ping' | 'dns' | 'tcp' | 'tls' | 'http' | 'mtu'

const activeTool = ref<DiagTool>('ping')
const tools: Array<{ id: DiagTool; label: string }> = [
  { id: 'ping', label: 'Ping' },
  { id: 'dns', label: 'DNS' },
  { id: 'tcp', label: 'TCP' },
  { id: 'tls', label: 'TLS' },
  { id: 'http', label: 'HTTP' },
  { id: 'mtu', label: 'MTU' },
]

const pingTarget = ref('8.8.8.8')
const pingCount = ref(4)
const dnsHostname = ref('example.com')
const dnsRecordType = ref('A')
const tcpTarget = ref('example.com')
const tcpPort = ref(443)
const tlsTarget = ref('example.com')
const tlsPort = ref(443)
const httpUrl = ref('https://example.com')
const httpMethod = ref('GET')
const httpFollowRedirects = ref(true)
const mtuTarget = ref('8.8.8.8')

const diagRunning = ref(false)
const diagError = ref<string | null>(null)

function statusClass(status: unknown): string {
  const s = String(status ?? '').toLowerCase()
  if (s === 'success' || s === 'ok' || s === 'completed') return 'badge-good'
  if (s === 'timeout' || s === 'degraded') return 'badge-warn'
  if (s === 'error' || s === 'failed' || s === 'refused') return 'badge-bad'
  return 'badge-neutral'
}

async function runDiagnostic() {
  diagRunning.value = true
  diagError.value = null
  try {
    let payload: Record<string, unknown>
    switch (activeTool.value) {
      case 'ping':
        payload = { target: pingTarget.value.trim(), count: pingCount.value }
        break
      case 'dns':
        payload = { hostname: dnsHostname.value.trim(), record_type: dnsRecordType.value }
        break
      case 'tcp':
        payload = { target: tcpTarget.value.trim(), port: tcpPort.value }
        break
      case 'tls':
        payload = { target: tlsTarget.value.trim(), port: tlsPort.value }
        break
      case 'http':
        payload = { url: httpUrl.value.trim(), method: httpMethod.value, follow_redirects: httpFollowRedirects.value }
        break
      case 'mtu':
        payload = { target: mtuTarget.value.trim() }
        break
    }
    await store.runDiagnostic(activeTool.value, payload)
    if (store.error) diagError.value = store.error
  } finally {
    diagRunning.value = false
  }
}

const diagnosticResult = computed(() => store.diagnostic)
const diagnosticStatus = computed(() => diagnosticResult.value?.['status'])
const diagnosticEntries = computed(() => {
  const d = diagnosticResult.value
  if (!d || typeof d !== 'object') return []
  return Object.entries(d as Record<string, unknown>).map(([key, value]) => ({ key, value }))
})

const sessionProfile = ref<'quick' | 'standard' | 'deep'>('standard')
const sessionSpeedtest = ref(false)
const sessionTargetsInput = ref('')

const sessionId = computed(() => store.session?.id ?? null)
const sessionStatus = computed(() => store.session?.status ?? null)
const sessionRunning = computed(() => sessionStatus.value === 'running')
const sessionLoading = ref(false)
const sessionError = ref<string | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null
const POLL_INTERVAL_MS = 2000
const POLL_MAX_MS = 150000
let pollElapsedMs = 0

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling(id: string) {
  stopPolling()
  pollElapsedMs = 0
  pollTimer = setInterval(async () => {
    pollElapsedMs += POLL_INTERVAL_MS
    await store.loadSession(id)
    if (store.sessionResults) {
      await store.loadSessionResults(id)
    }
    const status = store.session?.status
    if (status !== 'running' || pollElapsedMs >= POLL_MAX_MS) {
      stopPolling()
    }
  }, POLL_INTERVAL_MS)
}

function parseTargets(): string[] {
  return sessionTargetsInput.value
    .split(',')
    .map(t => t.trim())
    .filter(t => t.length > 0)
}

async function startSession() {
  sessionError.value = null
  sessionLoading.value = true
  try {
    await store.startSession(sessionProfile.value, sessionSpeedtest.value, parseTargets())
    if (store.error) {
      sessionError.value = store.error
      return
    }
    const id = store.session?.id
    if (id) {
      await store.loadSessionResults(id)
      startPolling(id)
    }
  } finally {
    sessionLoading.value = false
  }
}

async function cancelSession() {
  const id = sessionId.value
  if (!id) return
  stopPolling()
  sessionLoading.value = true
  try {
    await store.cancelSession(id)
    if (store.error) sessionError.value = store.error
  } finally {
    sessionLoading.value = false
  }
}

async function exportSession(format: 'json' | 'csv' | 'md') {
  const id = sessionId.value
  if (!id) return
  await store.exportSession(id, format)
  if (store.error) sessionError.value = store.error
}

onBeforeUnmount(() => {
  stopPolling()
})

const results = computed(() => store.sessionResults)

function formatPayload(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
</script>

<template>
  <div class="internet-diagnostics-page" data-testid="internet-diagnostics-page">
    <header class="page-header">
      <h1>Diagnostic Lab</h1>
      <p class="page-subtitle">เครื่องมือวินิจฉัยเครือข่าย (Ping/DNS/TCP/TLS/HTTP/MTU) และ Troubleshooting Session พร้อม Export รายงาน</p>
    </header>

    <section class="diag-section" data-testid="diagnostic-section">
      <div class="section-header">
        <h2>Quick Diagnostics</h2>
      </div>

      <div class="tool-tabs" data-testid="diag-tool-tabs">
        <button
          v-for="t in tools"
          :key="t.id"
          type="button"
          class="tool-tab"
          :class="{ active: activeTool === t.id }"
          :data-testid="`diag-tab-${t.id}`"
          @click="activeTool = t.id"
        >
          {{ t.label }}
        </button>
      </div>

      <div class="diag-form" data-testid="diag-form">
        <template v-if="activeTool === 'ping'">
          <div class="form-row">
            <label for="diag-ping-target">Target</label>
            <input id="diag-ping-target" v-model="pingTarget" type="text" placeholder="8.8.8.8" data-testid="diag-target-input" />
          </div>
          <div class="form-row">
            <label for="diag-ping-count">Count</label>
            <input id="diag-ping-count" v-model.number="pingCount" type="number" min="1" max="10" data-testid="diag-count-input" />
          </div>
        </template>

        <template v-else-if="activeTool === 'dns'">
          <div class="form-row">
            <label for="diag-dns-hostname">Hostname</label>
            <input id="diag-dns-hostname" v-model="dnsHostname" type="text" placeholder="example.com" data-testid="diag-hostname-input" />
          </div>
          <div class="form-row">
            <label for="diag-dns-record-type">Record Type</label>
            <select id="diag-dns-record-type" v-model="dnsRecordType" data-testid="diag-record-type-select">
              <option value="A">A</option>
              <option value="AAAA">AAAA</option>
            </select>
          </div>
        </template>

        <template v-else-if="activeTool === 'tcp'">
          <div class="form-row">
            <label for="diag-tcp-target">Target</label>
            <input id="diag-tcp-target" v-model="tcpTarget" type="text" placeholder="example.com" data-testid="diag-target-input-tcp" />
          </div>
          <div class="form-row">
            <label for="diag-tcp-port">Port</label>
            <input id="diag-tcp-port" v-model.number="tcpPort" type="number" min="1" max="65535" data-testid="diag-port-input" />
          </div>
        </template>

        <template v-else-if="activeTool === 'tls'">
          <div class="form-row">
            <label for="diag-tls-target">Target</label>
            <input id="diag-tls-target" v-model="tlsTarget" type="text" placeholder="example.com" data-testid="diag-target-input-tls" />
          </div>
          <div class="form-row">
            <label for="diag-tls-port">Port</label>
            <input id="diag-tls-port" v-model.number="tlsPort" type="number" min="1" max="65535" data-testid="diag-port-input-tls" />
          </div>
        </template>

        <template v-else-if="activeTool === 'http'">
          <div class="form-row">
            <label for="diag-http-url">URL</label>
            <input id="diag-http-url" v-model="httpUrl" type="text" placeholder="https://example.com" data-testid="diag-url-input" />
          </div>
          <div class="form-row">
            <label for="diag-http-method">Method</label>
            <select id="diag-http-method" v-model="httpMethod" data-testid="diag-method-select">
              <option value="GET">GET</option>
              <option value="HEAD">HEAD</option>
              <option value="POST">POST</option>
            </select>
          </div>
          <div class="form-row">
            <label for="diag-http-follow">Follow Redirects</label>
            <input id="diag-http-follow" v-model="httpFollowRedirects" type="checkbox" data-testid="diag-follow-redirects-checkbox" />
          </div>
        </template>

        <template v-else>
          <div class="form-row">
            <label for="diag-mtu-target">Target</label>
            <input id="diag-mtu-target" v-model="mtuTarget" type="text" placeholder="8.8.8.8" data-testid="diag-target-input-mtu" />
          </div>
        </template>

        <button
          type="button"
          class="btn-primary"
          :disabled="diagRunning"
          data-testid="diag-run-btn"
          @click="runDiagnostic"
        >
          <span v-if="diagRunning" class="spinner-sm" aria-hidden="true"></span>
          {{ diagRunning ? 'Running...' : 'Run' }}
        </button>
      </div>

      <div v-if="diagError" class="error-state" data-testid="diag-error-state">
        <p class="error-message">{{ diagError }}</p>
      </div>

      <div v-else-if="diagnosticResult" class="diag-result-panel" data-testid="diag-result-panel">
        <div class="result-header">
          <span>ผลลัพธ์ {{ activeTool.toUpperCase() }}</span>
          <span class="status-badge" :class="statusClass(diagnosticStatus)" data-testid="diag-status-badge">
            {{ String(diagnosticStatus ?? '—') }}
          </span>
        </div>
        <table class="result-table">
          <tbody>
            <tr v-for="entry in diagnosticEntries" :key="entry.key">
              <th scope="row">{{ entry.key }}</th>
              <td class="mono">{{ formatPayload(entry.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="diag-placeholder" data-testid="diag-placeholder">
        เลือกเครื่องมือ กรอกข้อมูล แล้วกด Run เพื่อดูผลลัพธ์
      </div>
    </section>

    <section class="session-section" data-testid="session-section">
      <div class="section-header">
        <h2>Troubleshooting Session</h2>
        <span v-if="sessionStatus" class="status-badge" :class="statusClass(sessionStatus)" data-testid="session-status-badge">
          {{ sessionStatus }}
        </span>
      </div>

      <div class="session-form" data-testid="session-form">
        <div class="form-row">
          <label for="session-profile">Profile</label>
          <select id="session-profile" v-model="sessionProfile" data-testid="session-profile-select">
            <option value="quick">Quick (30s)</option>
            <option value="standard">Standard (60s)</option>
            <option value="deep">Deep (120s)</option>
          </select>
        </div>
        <div class="form-row">
          <label for="session-speedtest">Include Speedtest</label>
          <input id="session-speedtest" v-model="sessionSpeedtest" type="checkbox" data-testid="session-speedtest-checkbox" />
        </div>
        <div class="form-row">
          <label for="session-targets">Custom Targets</label>
          <input
            id="session-targets"
            v-model="sessionTargetsInput"
            type="text"
            placeholder="example.com, 1.1.1.1"
            data-testid="session-targets-input"
          />
        </div>
        <div class="session-actions">
          <button
            type="button"
            class="btn-primary"
            :disabled="sessionLoading || sessionRunning"
            data-testid="session-start-btn"
            @click="startSession"
          >
            <span v-if="sessionLoading" class="spinner-sm" aria-hidden="true"></span>
            {{ sessionLoading ? 'Starting...' : 'Start Session' }}
          </button>
          <button
            type="button"
            class="btn-secondary"
            :disabled="!sessionRunning"
            data-testid="session-cancel-btn"
            @click="cancelSession"
          >
            Cancel
          </button>
        </div>
      </div>

      <div v-if="sessionError" class="error-state" data-testid="session-error-state">
        <p class="error-message">{{ sessionError }}</p>
      </div>

      <div v-if="sessionId" class="session-results" data-testid="session-results">
        <div class="section-header">
          <h3>Results</h3>
          <div class="export-buttons">
            <button type="button" class="btn-secondary" data-testid="session-export-json" @click="exportSession('json')">Export JSON</button>
            <button type="button" class="btn-secondary" data-testid="session-export-csv" @click="exportSession('csv')">Export CSV</button>
            <button type="button" class="btn-secondary" data-testid="session-export-md" @click="exportSession('md')">Export MD</button>
          </div>
        </div>

        <table class="results-table" data-testid="session-results-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Type</th>
              <th>Time</th>
              <th>Payload</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in results" :key="row.sequence" data-testid="session-result-row">
              <td>{{ row.sequence }}</td>
              <td>{{ row.result_type }}</td>
              <td class="mono">{{ row.ts }}</td>
              <td class="mono payload-cell">{{ formatPayload(row.payload) }}</td>
            </tr>
            <tr v-if="!results.length">
              <td colspan="4" class="empty-row">ยังไม่มีผลลัพธ์</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.internet-diagnostics-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  margin-bottom: 0;
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

.diag-section,
.session-section {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 20px;
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

.section-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.tool-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.tool-tab {
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.tool-tab:hover {
  color: var(--text);
  border-color: var(--border-strong, var(--border));
}

.tool-tab.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 700;
}

.diag-form,
.session-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--panel-2, var(--panel));
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
  min-width: 140px;
}

.form-row input[type='text'],
.form-row input[type='number'],
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

.form-row input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
  cursor: pointer;
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

.btn-secondary {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: var(--radius-btn);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}

.btn-secondary:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.session-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.export-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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

.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  font-family: var(--font-mono, ui-monospace, monospace);
}

.badge-good {
  background: color-mix(in srgb, var(--good) 15%, transparent);
  color: var(--good);
}

.badge-warn {
  background: color-mix(in srgb, var(--warn) 15%, transparent);
  color: var(--warn);
}

.badge-bad {
  background: color-mix(in srgb, var(--bad) 15%, transparent);
  color: var(--bad);
}

.badge-neutral {
  background: var(--panel-2, transparent);
  color: var(--text-dim);
  border: 1px solid var(--border);
}

.diag-result-panel {
  background: var(--panel-2, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.result-table th,
.result-table td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.result-table th {
  color: var(--text-dim);
  font-weight: 500;
  width: 220px;
}

.mono {
  font-family: var(--font-mono, ui-monospace, monospace);
  word-break: break-all;
}

.diag-placeholder,
.error-state {
  background: var(--panel-2, transparent);
  border: 1px dashed var(--border);
  border-radius: var(--radius-card);
  padding: 24px;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
}

.error-state {
  border-style: solid;
}

.error-message {
  margin: 0;
  color: var(--bad);
  font-size: 14px;
}

.results-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.results-table th,
.results-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.results-table thead th {
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.payload-cell {
  max-width: 480px;
}

.empty-row {
  text-align: center;
  color: var(--text-dim);
  padding: 20px;
}
</style>
