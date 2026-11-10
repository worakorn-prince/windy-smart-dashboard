<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'

type Dataset = 'single' | 'all'

interface Kpis {
  total_tasks: number
  done: number
  failed: number
  cancelled: number
  success_rate: number
  total_tool_calls: number
  recoveries: number
  review_fails: number
  tokens_total: number
  open_alerts: number
}

interface TaskItem {
  task: string
  done: boolean
  sessions: number
  tool_calls: number
  recovery: number
  review_loop: number
  time_to_DONE: string | null
  tokens: number
  recovery_tokens: number
  review_passed: number
  denied: number
}

interface TimelineItem {
  time: string | null
  event: string
  task: string | null
}

interface AlertItem {
  time: string | null
  event: string
  task: string | null
}

interface ViewerData {
  generated_at: string
  kpis: Kpis
  per_task: TaskItem[]
  timeline: TimelineItem[]
  alerts: AlertItem[]
}

const dataset = ref<Dataset>('single')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const data = ref<ViewerData | null>(null)

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'windy-dashboard',
  }
  try {
    const token = localStorage.getItem('dashboard:adminToken')
    if (token) headers['X-Admin-Token'] = token
  } catch {
    // localStorage unavailable
  }
  return headers
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch(`/api/viewer/${dataset.value}`, {
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
    })
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}))
      const hint = detail?.detail?.hint ?? 'โหลดข้อมูลไม่สำเร็จ'
      throw new Error(hint)
    }
    const body = await resp.json()
    data.value = body.data
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'โหลดข้อมูลไม่สำเร็จ'
  } finally {
    loading.value = false
  }
}

async function rebuild() {
  error.value = ''
  notice.value = ''
  try {
    const resp = await fetch('/api/viewer/rebuild', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ aggregate: dataset.value === 'all' }),
    })
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}))
      const code = detail?.detail?.code ?? 'REBUILD_FAILED'
      const text = detail?.detail?.text ?? 'Rebuild ล้มเหลว'
      const hint = detail?.detail?.hint ?? 'ลองใหม่อีกครั้ง'
      throw new Error(`${code}: ${text} — ${hint}`)
    }
    notice.value = 'Rebuild สำเร็จ — กำลังโหลดข้อมูลใหม่…'
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Rebuild ไม่สำเร็จ'
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('th-TH', {
      dateStyle: 'medium',
      timeStyle: 'medium',
    })
  } catch {
    return iso
  }
}

function formatNumber(n: number): string {
  return n.toLocaleString('th-TH')
}

function formatPercent(pct: number): string {
  return `${(pct * 100).toFixed(1)}%`
}

const kpiItems = computed(() => {
  if (!data.value) return [] as { label: string; value: string; class?: string }[]
  const k = data.value.kpis
  return [
    { label: 'Total tasks', value: formatNumber(k.total_tasks) },
    { label: 'Done', value: formatNumber(k.done), class: 'good' },
    { label: 'Failed', value: formatNumber(k.failed), class: k.failed ? 'bad' : '' },
    { label: 'Cancelled', value: formatNumber(k.cancelled), class: k.cancelled ? 'warn' : '' },
    { label: 'Success rate', value: formatPercent(k.success_rate) },
    { label: 'Tool calls', value: formatNumber(k.total_tool_calls) },
    { label: 'Tokens', value: formatNumber(k.tokens_total) },
    { label: 'Recoveries', value: formatNumber(k.recoveries), class: k.recoveries ? 'good' : '' },
    { label: 'Review fails', value: formatNumber(k.review_fails), class: k.review_fails ? 'bad' : '' },
    { label: 'Open alerts', value: formatNumber(k.open_alerts), class: k.open_alerts ? 'bad' : '' },
  ]
})

const recentTimeline = computed(() => {
  if (!data.value) return [] as TimelineItem[]
  return data.value.timeline.slice(-20).reverse()
})

function textOrDash(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—'
  return String(v)
}

onMounted(() => {
  load()
})
</script>

<template>
  <div class="viewer-page" data-testid="viewer-page">
    <div class="page-head">
      <h2>Viewer <span class="badge info">Scopeboard</span></h2>
      <div class="head-actions">
        <div class="dataset-toggle" data-testid="viewer-dataset-toggle">
          <button
            :class="['btn', { primary: dataset === 'single' }]"
            @click="dataset = 'single'; load()"
            :disabled="loading"
          >
            Single project
          </button>
          <button
            :class="['btn', { primary: dataset === 'all' }]"
            @click="dataset = 'all'; load()"
            :disabled="loading"
          >
            All projects
          </button>
        </div>
        <button class="btn" @click="load" :disabled="loading" data-testid="viewer-refresh">
          {{ loading ? 'กำลังโหลด…' : 'Refresh' }}
        </button>
        <button class="btn primary" @click="rebuild" :disabled="loading" data-testid="viewer-rebuild">
          Rebuild
        </button>
      </div>
    </div>

    <div v-if="error" class="banner error" role="alert">
      <span>{{ error }}</span>
      <button class="btn tiny" @click="error = ''">ปิด</button>
    </div>
    <div v-if="notice" class="banner notice" role="status">
      <span>{{ notice }}</span>
      <button class="btn tiny" @click="notice = ''">ปิด</button>
    </div>

    <div v-if="loading && !data" class="card" style="text-align:center; padding:40px;">
      <p class="muted">กำลังโหลดข้อมูล…</p>
    </div>

    <template v-else-if="data">
      <div class="grid" data-testid="viewer-kpis">
        <div class="card kpi-card" v-for="item in kpiItems" :key="item.label">
          <div class="row">
            <span class="label">{{ item.label }}</span>
            <span class="value" :class="item.class">{{ item.value }}</span>
          </div>
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <h3>Per-task</h3>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Done</th>
                  <th>Sessions</th>
                  <th>Tool calls</th>
                  <th>Recovery</th>
                  <th>Review loop</th>
                  <th>Time to DONE</th>
                  <th>Tokens</th>
                  <th>Recovery tokens</th>
                  <th>Review passed</th>
                  <th>Denied</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="task in data.per_task" :key="task.task">
                  <td class="text-truncate" v-auto-tip>{{ task.task }}</td>
                  <td><span class="badge" :class="task.done ? 'low' : 'medium'">{{ task.done ? '✓' : '—' }}</span></td>
                  <td>{{ formatNumber(task.sessions) }}</td>
                  <td>{{ formatNumber(task.tool_calls) }}</td>
                  <td>{{ formatNumber(task.recovery) }}</td>
                  <td>{{ formatNumber(task.review_loop) }}</td>
                  <td>{{ textOrDash(task.time_to_DONE) }}</td>
                  <td>{{ formatNumber(task.tokens) }}</td>
                  <td>{{ formatNumber(task.recovery_tokens) }}</td>
                  <td>{{ formatNumber(task.review_passed) }}</td>
                  <td>{{ formatNumber(task.denied) }}</td>
                </tr>
                <tr v-if="!data.per_task.length">
                  <td colspan="11" class="muted" style="text-align:center;">ไม่มีข้อมูล task</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <h3>Timeline (ล่าสุด 20 รายการ)</h3>
          <div class="card-scroll">
            <ul class="timeline-list">
              <li v-for="(item, i) in recentTimeline" :key="i" class="timeline-item">
                <span class="timeline-time">{{ formatDate(item.time ?? '') }}</span>
                <span class="timeline-event">{{ item.event }}</span>
                <span v-if="item.task" class="timeline-task">{{ item.task }}</span>
              </li>
              <li v-if="!recentTimeline.length" class="muted">ไม่มี timeline</li>
            </ul>
          </div>
        </div>

        <div class="card" v-if="data.alerts && data.alerts.length">
          <h3>Alerts</h3>
          <div class="card-scroll">
            <ul class="timeline-list">
              <li v-for="(item, i) in data.alerts" :key="i" class="timeline-item">
                <span class="timeline-time">{{ formatDate(item.time ?? '') }}</span>
                <span class="timeline-event">{{ item.event }}</span>
                <span v-if="item.task" class="timeline-task">{{ item.task }}</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="card">
          <h3>Generated at</h3>
          <p class="muted">{{ formatDate(data.generated_at) }}</p>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="card" style="text-align:center; padding:40px;">
        <p class="muted">ยังไม่มีข้อมูล — กด Rebuild เพื่อสร้างข้อมูลใหม่</p>
        <button class="btn primary" @click="rebuild" :disabled="loading" data-testid="viewer-rebuild-empty">
          Rebuild
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.viewer-page { display: flex; flex-direction: column; gap: 16px; }

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.page-head h2 { margin: 0; font-size: 18px; display: flex; align-items: center; gap: 10px; }
.head-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.dataset-toggle { display: flex; gap: 4px; }

.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.banner.error { border-color: var(--bad); color: var(--bad); }
.banner.notice { border-color: var(--info); color: var(--info); }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }

.kpi-card { text-align: center; }
.kpi-card .row { justify-content: center; }
.kpi-card .value { font-size: 1.5em; font-weight: 700; }
.kpi-card .value.good { color: var(--good); }
.kpi-card .value.bad { color: var(--bad); }
.kpi-card .value.warn { color: var(--warn); }

.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }

.timeline-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.timeline-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
}
.timeline-time { color: var(--muted); font-size: 11px; white-space: nowrap; min-width: 140px; }
.timeline-event { font-weight: 600; color: var(--accent); }
.timeline-task { color: var(--info); font-size: 11px; background: var(--panel); padding: 1px 6px; border-radius: 3px; }

@media (max-width: 640px) {
  .page-head { flex-direction: column; align-items: stretch; }
  .head-actions { justify-content: flex-start; }
  .dataset-toggle { width: 100%; }
  .dataset-toggle button { flex: 1; }
}
</style>