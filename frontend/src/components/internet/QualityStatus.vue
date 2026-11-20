<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useInternetStore } from '@/stores/internet'

const store = useInternetStore()

const props = defineProps<{
  autoLoad?: boolean
  range?: '5m' | '1h' | '6h' | '24h' | '7d' | '30d'
}>()

const range = computed(() => props.range ?? '1h')

const overall = computed(() => store.qualityStatus?.overall)
const targets = computed(() => store.qualityStatus?.targets ?? {})
const evidence = computed(() => overall.value?.evidence ?? [])

const badgeClass = computed(() => {
  const status = overall.value?.status
  switch (status) {
    case 'good': return 'badge-good'
    case 'degraded': return 'badge-degraded'
    case 'poor': return 'badge-poor'
    default: return 'badge-unknown'
  }
})

const badgeLabel = computed(() => overall.value?.badge ?? 'Unknown')

const confidencePct = computed(() => Math.round((overall.value?.confidence ?? 0) * 100))

function formatTimeAgo(ts: number | null): string {
  if (!ts) return '—'
  const diff = (Date.now() - ts * 1000) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function getDegradationClass(degraded: boolean): string {
  return degraded ? 'degraded-yes' : 'degraded-no'
}

onMounted(async () => {
  if (props.autoLoad !== false) {
    await store.loadQualityStatus(range.value)
  }
})
</script>

<template>
  <div class="quality-status" data-testid="quality-status">
    <header class="status-header">
      <h3 class="status-title">คุณภาพการเชื่อมต่อโดยรวม</h3>
      <div class="status-badge-wrapper">
        <span class="status-badge" :class="badgeClass" data-testid="quality-status-badge">
          {{ badgeLabel }}
        </span>
        <span v-if="overall" class="confidence" :data-testid="`quality-confidence-${overall.status}`">
          ความเชื่อมั่น: {{ confidencePct }}%
        </span>
      </div>
    </header>

    <div v-if="store.loading && !evidence.length" class="loading-state" data-testid="quality-status-loading">
      <div class="spinner" aria-hidden="true"></div>
      <span>กำลังวิเคราะห์คุณภาพ...</span>
    </div>

    <div v-else-if="store.error" class="error-state" data-testid="quality-status-error">
      <p class="error-message">{{ store.error }}</p>
      <button @click="store.loadQualityStatus(range)" class="retry-btn">ลองใหม่</button>
    </div>

    <div v-else-if="!evidence.length" class="empty-state" data-testid="quality-status-empty">
      <p>ยังไม่มีข้อมูลสำหรับการประเมินคุณภาพ</p>
    </div>

    <div v-else class="evidence-grid" data-testid="quality-evidence-grid">
      <div
        v-for="(target, targetId) in targets"
        :key="targetId"
        class="evidence-card"
        :class="{ degraded: target.degraded }"
        :data-testid="`evidence-${targetId}`"
      >
        <div class="evidence-header">
          <h4 class="evidence-target-name">
            {{ targetId === 'primary' ? 'Primary (1.1.1.1)' : targetId === 'secondary' ? 'Secondary (8.8.8.8)' : 'Gateway' }}
          </h4>
          <span class="degradation-badge" :class="getDegradationClass(target.degraded)">
            {{ target.degraded ? 'ลดคุณภาพ' : 'ปกติ' }}
          </span>
        </div>

        <div class="evidence-metrics">
          <div class="metric-row">
            <span class="metric-label">เลตันซี (median)</span>
            <span class="metric-value" :class="target.latency_median_ms != null && target.latency_median_ms > 100 ? 'warn' : ''">
              {{ target.latency_median_ms != null ? target.latency_median_ms.toFixed(1) + ' ms' : '—' }}
            </span>
          </div>
          <div class="metric-row">
            <span class="metric-label">จิทเตอร์</span>
            <span class="metric-value" :class="target.jitter_ms != null && target.jitter_ms > 30 ? 'warn' : ''">
              {{ target.jitter_ms != null ? target.jitter_ms.toFixed(1) + ' ms' : '—' }}
            </span>
          </div>
          <div class="metric-row">
            <span class="metric-label">Packet Loss</span>
            <span class="metric-value" :class="target.loss_pct > 5 ? 'warn' : target.loss_pct > 1 ? 'warn' : ''">
              {{ target.loss_pct.toFixed(1) }}%
            </span>
          </div>
          <div class="metric-row">
            <span class="metric-label">ตัวอย่างล่าสุด</span>
            <span class="metric-value">{{ formatTimeAgo(target.last_probe_at) }}</span>
          </div>
          <div class="metric-row">
            <span class="metric-label">ตัวอย่างในช่วง</span>
            <span class="metric-value">{{ target.sample_count }}</span>
          </div>
        </div>

        <div v-if="target.degraded && target.degradation_reason" class="degradation-detail">
          <span class="degradation-label">เหตุผล:</span>
          <span class="degradation-reason">{{ target.degradation_reason }}</span>
          <span class="degradation-confidence">ความเชื่อมั่น: {{ Math.round(target.degradation_confidence * 100) }}%</span>
        </div>
      </div>
    </div>

    <div v-if="overall && overall.degraded_targets.length > 0" class="degradation-summary" data-testid="quality-degradation-summary">
      <h4>⚠️ พบการลดคุณภาพที่:</h4>
      <ul>
        <li v-for="t in overall.degraded_targets" :key="t">
          {{ t === 'primary' ? 'Primary (1.1.1.1)' : t === 'secondary' ? 'Secondary (8.8.8.8)' : 'Gateway' }}
        </li>
      </ul>
    </div>

    <div class="status-meta">
      <span class="meta-item">ช่วงเวลา: {{ range }}</span>
      <span class="meta-item">วิเคราะห์เมื่อ: {{ overall ? formatTimeAgo(overall.analyzed_at) : '—' }}</span>
    </div>
  </div>
</template>

<style scoped>
.quality-status {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.status-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.status-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.status-badge-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  padding: 6px 16px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.status-badge.badge-good { background: rgba(74, 222, 128, 0.15); color: var(--good); border: 1px solid var(--good); }
.status-badge.badge-degraded { background: rgba(251, 191, 36, 0.15); color: var(--warn); border: 1px solid var(--warn); }
.status-badge.badge-poor { background: rgba(248, 113, 113, 0.15); color: var(--bad); border: 1px solid var(--bad); }
.status-badge.badge-unknown { background: rgba(100, 116, 139, 0.15); color: var(--muted); border: 1px solid var(--border); }

.confidence {
  font-size: 11px;
  color: var(--muted);
  font-family: var(--font-mono);
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  gap: 12px;
  color: var(--muted);
  font-size: 13px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
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
  font-size: 13px;
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

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.evidence-card {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-ctl);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.evidence-card.degraded {
  border-color: var(--warn);
  background: color-mix(in srgb, var(--warn) 5%, var(--panel-2));
}

.evidence-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.evidence-target-name {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  font-family: var(--font-mono);
}

.degradation-badge {
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.degradation-badge.degraded-yes { background: rgba(251, 191, 36, 0.15); color: var(--warn); }
.degradation-badge.degraded-no { background: rgba(74, 222, 128, 0.15); color: var(--good); }

.evidence-metrics {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  font-family: var(--font-mono);
}

.metric-label {
  color: var(--muted);
}

.metric-value {
  color: var(--text);
  font-weight: 500;
}

.metric-value.warn {
  color: var(--warn);
}

.degradation-detail {
  margin-top: 4px;
  padding: 8px;
  background: var(--panel);
  border-radius: var(--radius-ctl);
  border: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-dim);
}

.degradation-label {
  font-weight: 600;
  color: var(--warn);
}

.degradation-reason {
  margin-left: 4px;
}

.degradation-confidence {
  margin-left: 8px;
  color: var(--muted);
}

.degradation-summary {
  padding: 12px;
  background: color-mix(in srgb, var(--warn) 8%, var(--panel-2));
  border: 1px solid var(--warn);
  border-radius: var(--radius-ctl);
}

.degradation-summary h4 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--warn);
}

.degradation-summary ul {
  margin: 0;
  padding-left: 20px;
  font-size: 12px;
  color: var(--text);
}

.degradation-summary li {
  margin: 4px 0;
}

.status-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--muted);
  font-family: var(--font-mono);
}

@media (max-width: 640px) {
  .evidence-grid {
    grid-template-columns: 1fr;
  }
}
</style>