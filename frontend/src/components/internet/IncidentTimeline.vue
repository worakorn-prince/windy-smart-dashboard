<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useInternetStore, type Incident } from '@/stores/internet'

const store = useInternetStore()

const STATUS_OPTIONS = ['all', 'active', 'acknowledged', 'resolved'] as const
const CATEGORY_OPTIONS = ['all', 'quality', 'dns', 'route', 'interface', 'tcp', 'gateway'] as const

const statusFilter = ref<string>('all')
const categoryFilter = ref<string>('all')

const expandedId = ref<string | null>(null)
const confirmingId = ref<string | null>(null)
const resolvingId = ref<string | null>(null)

const filteredIncidents = computed(() => {
  return store.incidents.filter(i => {
    if (statusFilter.value !== 'all' && i.status !== statusFilter.value) return false
    if (categoryFilter.value !== 'all' && i.category !== categoryFilter.value) return false
    return true
  })
})

const canResolve = (incident: Incident) => incident.status === 'active' || incident.status === 'acknowledged'

const severityClass = (severity: string) => {
  switch (severity.toUpperCase()) {
    case 'CRITICAL': return 'sev-critical'
    case 'HIGH': return 'sev-high'
    case 'MEDIUM': return 'sev-medium'
    case 'LOW': return 'sev-low'
    default: return 'sev-unknown'
  }
}

const statusClass = (status: string) => {
  switch (status) {
    case 'active': return 'st-active'
    case 'acknowledged': return 'st-acknowledged'
    case 'resolved': return 'st-resolved'
    default: return 'st-unknown'
  }
}

const confidencePct = (confidence: number) => Math.round(confidence * 100)

function formatEpoch(ts: number | null): string {
  if (ts === null || ts === undefined) return '—'
  return new Date(ts * 1000).toLocaleString()
}

function formatPayload(payload: Record<string, unknown>): string {
  try {
    return JSON.stringify(payload, null, 2)
  } catch {
    return String(payload)
  }
}

async function load() {
  await store.fetchIncidents()
}

function toggleEvidence(incident: Incident) {
  if (expandedId.value === incident.id) {
    expandedId.value = null
    return
  }
  expandedId.value = incident.id
  void store.fetchIncidentDetail(incident.id)
}

function askResolve(incident: Incident) {
  confirmingId.value = incident.id
}

function cancelResolve() {
  confirmingId.value = null
}

async function doResolve(incident: Incident) {
  confirmingId.value = null
  resolvingId.value = incident.id
  try {
    await store.resolveIncident(incident.id)
  } finally {
    resolvingId.value = null
  }
}

function setStatusFilter(status: string) {
  statusFilter.value = status
}

function setCategoryFilter(category: string) {
  categoryFilter.value = category
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="incident-timeline" data-testid="incident-timeline">
    <div class="timeline-header">
      <h2>Incidents</h2>
      <span v-if="!store.incidentsLoading" class="incident-count" data-testid="incident-count">
        {{ filteredIncidents.length }} / {{ store.incidents.length }} เหตุการณ์
      </span>
      <button class="reload-btn" data-testid="incidents-reload" :disabled="store.incidentsLoading" @click="load">
        รีโหลด
      </button>
    </div>

    <div class="filters" data-testid="incident-filters">
      <div class="filter-group">
        <span class="filter-label">สถานะ:</span>
        <button
          v-for="s in STATUS_OPTIONS"
          :key="s"
          class="filter-btn"
          :class="{ active: statusFilter === s }"
          :data-testid="`filter-status-${s}`"
          @click="setStatusFilter(s)"
        >
          {{ s }}
        </button>
      </div>
      <div class="filter-group">
        <span class="filter-label">หมวด:</span>
        <button
          v-for="c in CATEGORY_OPTIONS"
          :key="c"
          class="filter-btn"
          :class="{ active: categoryFilter === c }"
          :data-testid="`filter-category-${c}`"
          @click="setCategoryFilter(c)"
        >
          {{ c }}
        </button>
      </div>
    </div>

    <div v-if="store.incidentsLoading && store.incidents.length === 0" class="state-box" data-testid="incidents-loading">
      <div class="spinner" aria-hidden="true"></div>
      <span>กำลังโหลดเหตุการณ์...</span>
    </div>

    <div v-else-if="store.incidentsError" class="state-box error" data-testid="incidents-error">
      <span class="error-text">{{ store.incidentsError }}</span>
      <button class="retry-btn" @click="load">ลองใหม่</button>
    </div>

    <div v-else-if="store.incidents.length === 0" class="state-box empty" data-testid="incidents-empty">
      <span>ยังไม่มีเหตุการณ์ — baseline อาจยังไม่เพียงพอสำหรับการวิเคราะห์ (เป็นเรื่องปกติ)</span>
    </div>

    <div v-else-if="filteredIncidents.length === 0" class="state-box empty" data-testid="incidents-filter-empty">
      <span>ไม่มีเหตุการณ์ที่ตรงกับตัวกรอง</span>
    </div>

    <ul v-else class="timeline" data-testid="incident-list">
      <li
        v-for="incident in filteredIncidents"
        :key="incident.id"
        class="incident-row"
        :class="[severityClass(incident.severity), { expanded: expandedId === incident.id }]"
        :data-testid="`incident-row-${incident.id}`"
      >
        <div class="incident-main">
          <div class="incident-title-row">
            <span class="sev-badge" :class="severityClass(incident.severity)" :data-testid="`incident-severity-${incident.id}`">{{ incident.severity }}</span>
            <span class="st-badge" :data-testid="`incident-status-${incident.id}`">{{ incident.status }}</span>
            <span class="cat-badge" :data-testid="`incident-category-${incident.id}`">{{ incident.category }}</span>
            <strong class="incident-title">{{ incident.title }}</strong>
          </div>
          <div class="incident-meta">
            <span>เริ่ม: {{ formatEpoch(incident.started_at) }}</span>
            <span>สิ้นสุด: {{ formatEpoch(incident.ended_at) }}</span>
            <span>conf: {{ confidencePct(incident.confidence) }}%</span>
            <span class="analyzer">analyzer v{{ incident.analyzer_version }}</span>
          </div>
          <p v-if="incident.summary" class="incident-summary">{{ incident.summary }}</p>

          <div class="incident-actions">
            <button
              class="action-btn evidence-btn"
              :data-testid="`toggle-evidence-${incident.id}`"
              @click="toggleEvidence(incident)"
            >
              {{ expandedId === incident.id ? 'ซ่อนหลักฐาน' : 'ดูหลักฐาน' }}
            </button>
            <button
              v-if="canResolve(incident)"
              class="action-btn resolve-btn"
              :data-testid="`resolve-${incident.id}`"
              :disabled="resolvingId === incident.id"
              @click="askResolve(incident)"
            >
              {{ resolvingId === incident.id ? 'กำลัง resolve...' : 'Resolve' }}
            </button>
          </div>

          <div v-if="confirmingId === incident.id" class="confirm-box" :data-testid="`confirm-resolve-${incident.id}`">
            <span>ยืนยันการ resolve เหตุการณ์นี้?</span>
            <button class="action-btn confirm-yes" :data-testid="`confirm-yes-${incident.id}`" @click="doResolve(incident)">ยืนยัน</button>
            <button class="action-btn confirm-no" :data-testid="`confirm-no-${incident.id}`" @click="cancelResolve">ยกเลิก</button>
          </div>
        </div>

        <div v-if="expandedId === incident.id" class="evidence-panel" :data-testid="`evidence-panel-${incident.id}`">
          <div v-if="store.activeIncidentLoading" class="evidence-loading">กำลังโหลดหลักฐาน...</div>
          <template v-else>
            <div v-if="store.activeIncident?.id === incident.id && store.activeIncident?.summary" class="analyzer-note">
              <strong>บทวิเคราะห์:</strong> {{ store.activeIncident.summary }}
            </div>
            <div v-if="store.activeIncidentEvidence.length === 0" class="evidence-empty">ไม่มีหลักฐานสำหรับเหตุการณ์นี้</div>
            <div
              v-for="ev in store.activeIncidentEvidence"
              :key="ev.id"
              class="evidence-item"
              :data-testid="`evidence-item-${ev.id}`"
            >
              <div class="evidence-head">
                <span class="evidence-type">{{ ev.evidence_type }}</span>
                <span class="evidence-time">{{ formatEpoch(ev.observed_at) }}</span>
              </div>
              <pre class="evidence-payload">{{ formatPayload(ev.payload) }}</pre>
            </div>
          </template>
        </div>
      </li>
    </ul>

    <div v-if="store.resolveConflictMessage" class="conflict-box" data-testid="resolve-conflict">
      <span>{{ store.resolveConflictMessage }}</span>
    </div>
  </section>
</template>

<style scoped>
.incident-timeline {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 20px;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.timeline-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}

.incident-count {
  font-size: 12px;
  color: var(--muted);
}

.reload-btn {
  margin-left: auto;
  padding: 4px 12px;
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: var(--radius-btn);
  cursor: pointer;
  font-size: 12px;
}

.reload-btn:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--border-strong);
}

.reload-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.filters {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 14px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-label {
  font-size: 12px;
  color: var(--muted);
  min-width: 48px;
}

.filter-btn {
  padding: 3px 10px;
  background: transparent;
  color: var(--text-dim);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 11px;
  cursor: pointer;
  transition: color 0.15s ease, background 0.15s ease;
}

.filter-btn:hover {
  color: var(--text);
  border-color: var(--border-strong);
}

.filter-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--on-accent);
  font-weight: 700;
}

.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px;
  background: var(--panel-2);
  border: 1px dashed var(--border);
  border-radius: var(--radius-card);
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}

.state-box.error .error-text {
  color: var(--bad);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.retry-btn {
  padding: 6px 14px;
  background: var(--accent);
  color: var(--on-accent);
  border: none;
  border-radius: var(--radius-btn);
  font-weight: 600;
  cursor: pointer;
  font-size: 12px;
}

.retry-btn:hover {
  background: var(--accent-strong);
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.incident-row {
  border-left: 4px solid var(--border);
  background: var(--panel-2);
  border-radius: 8px;
  padding: 12px 14px;
}

.incident-row.sev-critical { border-left-color: var(--bad, #e5484d); }
.incident-row.sev-high { border-left-color: #f5a524; }
.incident-row.sev-medium { border-left-color: #eab308; }
.incident-row.sev-low { border-left-color: #22c55e; }
.incident-row.sev-unknown { border-left-color: var(--border-strong); }

.incident-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.incident-title {
  color: var(--text);
  font-size: 14px;
}

.sev-badge,
.st-badge,
.cat-badge {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--text-dim);
}

.sev-badge.sev-critical { background: rgba(229, 72, 77, 0.15); color: var(--bad, #e5484d); border-color: transparent; }
.sev-badge.sev-high { background: rgba(245, 165, 36, 0.15); color: #f5a524; border-color: transparent; }
.sev-badge.sev-medium { background: rgba(234, 179, 8, 0.15); color: #eab308; border-color: transparent; }
.sev-badge.sev-low { background: rgba(34, 197, 94, 0.15); color: #22c55e; border-color: transparent; }

.st-badge.st-active { background: rgba(229, 72, 77, 0.12); color: var(--bad, #e5484d); border-color: transparent; }
.st-badge.st-acknowledged { background: rgba(245, 165, 36, 0.12); color: #f5a524; border-color: transparent; }
.st-badge.st-resolved { background: rgba(34, 197, 94, 0.12); color: #22c55e; border-color: transparent; }

.incident-meta {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 11px;
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--muted);
}

.incident-summary {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
}

.incident-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.action-btn {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-btn);
  color: var(--text-dim);
  cursor: pointer;
  font-size: 12px;
}

.action-btn:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--border-strong);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.resolve-btn {
  color: var(--accent);
  border-color: var(--accent);
}

.resolve-btn:hover:not(:disabled) {
  background: var(--accent);
  color: var(--on-accent);
}

.confirm-box {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 8px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--text);
}

.confirm-yes {
  color: var(--on-accent);
  background: var(--accent);
  border-color: var(--accent);
}

.conflict-box {
  margin-top: 12px;
  padding: 10px 14px;
  background: rgba(245, 165, 36, 0.12);
  border: 1px solid #f5a524;
  border-radius: 8px;
  color: #f5a524;
  font-size: 12px;
}

.evidence-panel {
  margin-top: 12px;
  padding: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.evidence-loading,
.evidence-empty {
  font-size: 12px;
  color: var(--muted);
}

.analyzer-note {
  font-size: 12px;
  color: var(--text-dim);
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--border);
}

.evidence-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
}

.evidence-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 11px;
  margin-bottom: 6px;
}

.evidence-type {
  font-weight: 700;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.evidence-time {
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--muted);
}

.evidence-payload {
  margin: 0;
  font-size: 11px;
  font-family: var(--font-mono, ui-monospace, monospace);
  color: var(--text-dim);
  background: var(--panel-2);
  border-radius: 4px;
  padding: 8px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
