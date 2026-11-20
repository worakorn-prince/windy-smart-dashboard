<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { DnsComparisonResult } from '@/stores/internet'

const props = defineProps<{
  modelValue: boolean
  comparison: DnsComparisonResult[]
  hostname: string
  recordType: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'close'): void
}>()

const localVisible = ref(props.modelValue)

watch(() => props.modelValue, (val) => {
  localVisible.value = val
})

watch(localVisible, (val) => {
  if (!val) emit('close')
  emit('update:modelValue', val)
})

const sortedResults = computed(() => {
  return [...props.comparison].sort((a, b) => {
    if (a.duration_ms === null && b.duration_ms === null) return 0
    if (a.duration_ms === null) return 1
    if (b.duration_ms === null) return -1
    return a.duration_ms - b.duration_ms
  })
})

const fastestResult = computed(() => {
  const valid = props.comparison.filter(r => r.duration_ms !== null && r.status === 'success')
  if (!valid.length) return null
  return valid.reduce((min, r) => r.duration_ms! < min.duration_ms! ? r : min)
})

function getStatusClass(result: DnsComparisonResult): string {
  if (result.status === 'success') return 'status-ok'
  if (result.status === 'timeout') return 'status-timeout'
  if (result.status === 'error') return 'status-error'
  return 'status-unknown'
}

function getStatusLabel(result: DnsComparisonResult): string {
  switch (result.status) {
    case 'success': return 'สำเร็จ'
    case 'timeout': return 'หมดเวลา'
    case 'error': return `ข้อผิดพลาด: ${result.error_code ?? 'unknown'}`
    default: return 'ไม่ทราบ'
  }
}

function formatDuration(ms: number | null): string {
  if (ms === null) return '—'
  return `${ms.toFixed(1)} ms`
}

function closeModal() {
  localVisible.value = false
}
</script>

<template>
  <Transition name="modal-fade">
    <div v-if="localVisible" class="modal-overlay" @click="closeModal" data-testid="dns-comparison-overlay">
      <div class="modal-content" @click.stop data-testid="dns-comparison-modal">
        <header class="modal-header">
          <h2>เปรียบเทียบ DNS Resolver</h2>
          <div class="query-info">
            <span class="query-hostname">{{ hostname }}</span>
            <span class="query-type">{{ recordType }}</span>
          </div>
        </header>

        <div class="modal-body">
          <div v-if="!comparison?.length" class="empty-state">
            <p>ไม่มีข้อมูลการเปรียบเทียบ</p>
          </div>

          <div v-else class="comparison-table-wrapper">
            <table class="comparison-table" data-testid="dns-comparison-table">
              <thead>
                <tr>
                  <th>Resolver</th>
                  <th>Method</th>
                  <th>Latency</th>
                  <th>Status</th>
                  <th>Answers</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="result in sortedResults"
                  :key="result.resolver"
                  :class="{ 'fastest': fastestResult && result.resolver === fastestResult.resolver }"
                  :data-testid="`comparison-row-${result.resolver}`"
                >
                  <td class="resolver-col">{{ result.resolver }}</td>
                  <td class="method-col">{{ result.probe_method }}</td>
                  <td class="latency-col">
                    <span :class="{ 'fastest-badge': fastestResult && result.resolver === fastestResult.resolver && result.duration_ms !== null }">
                      {{ formatDuration(result.duration_ms) }}
                    </span>
                  </td>
                  <td class="status-col">
                    <span class="status-badge" :class="getStatusClass(result)">
                      {{ getStatusLabel(result) }}
                    </span>
                  </td>
                  <td class="answers-col">{{ result.answer_count }}</td>
                  <td class="actions-col">
                    <button
                      v-if="result.status === 'success' && result.duration_ms !== null && fastestResult && result.resolver === fastestResult.resolver"
                      class="badge-fastest"
                      type="button"
                    >
                      เร็วที่สุด
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="fastestResult" class="summary" data-testid="dns-comparison-summary">
            <span class="summary-icon">⚡</span>
            <span class="summary-text">
              เร็วที่สุด: <strong>{{ fastestResult.resolver }}</strong> ({{ formatDuration(fastestResult.duration_ms) }})
            </span>
          </div>
        </div>

        <footer class="modal-footer">
          <button type="button" class="btn-primary" @click="closeModal" data-testid="dns-comparison-close">ปิด</button>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 20px;
  animation: fadeIn 0.15s ease;
}

.modal-content {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  width: 100%;
  max-width: 720px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slideUp 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.query-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.query-hostname {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.query-type {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  color: var(--muted);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--muted);
  font-size: 14px;
}

.comparison-table-wrapper {
  overflow-x: auto;
}

.comparison-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.comparison-table th,
.comparison-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.comparison-table th {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--muted);
  font-weight: 600;
  background: var(--panel-2);
  position: sticky;
  top: 0;
}

.comparison-table tr:hover td {
  background: var(--panel-2);
}

.comparison-table tr.fastest td {
  background: rgba(34, 211, 238, 0.08);
}

.resolver-col {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
}

.method-col {
  font-size: 11px;
  color: var(--text-dim);
  font-family: var(--font-mono, ui-monospace, monospace);
}

.latency-col {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 500;
  color: var(--text);
}

.fastest-badge {
  background: linear-gradient(135deg, #22d3ee, #06b6d4);
  color: #00171c;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  display: inline-block;
}

.status-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}

.status-ok { background: rgba(34, 211, 238, 0.15); color: #22d3ee; }
.status-timeout { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.status-error { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.status-unknown { background: rgba(100, 116, 139, 0.15); color: #64748b; }

.answers-col {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-weight: 500;
  color: var(--text);
  text-align: center;
  width: 60px;
}

.actions-col { width: 80px; }

.badge-fastest {
  background: linear-gradient(135deg, #22d3ee, #06b6d4);
  color: #00171c;
  border: none;
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: default;
}

.summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 16px;
  padding: 12px 16px;
  background: rgba(34, 211, 238, 0.1);
  border: 1px solid rgba(34, 211, 238, 0.3);
  border-radius: var(--radius-ctl);
}

.summary-icon { font-size: 16px; }

.summary-text {
  font-size: 13px;
  color: var(--text);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  gap: 8px;
}

.btn-primary {
  background: var(--accent);
  color: var(--on-accent);
  border: none;
  padding: 8px 16px;
  border-radius: var(--radius-btn);
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}

.btn-primary:hover {
  background: var(--accent-strong);
}

@media (max-width: 640px) {
  .modal-content {
    max-height: 90vh;
  }

  .comparison-table th,
  .comparison-table td {
    padding: 8px 8px;
    font-size: 12px;
  }

  .resolver-col {
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>