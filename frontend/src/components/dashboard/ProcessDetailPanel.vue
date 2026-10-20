<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

interface ProcessNode {
  pid: number
  name: string
  children: ProcessNode[]
}

interface ProcessPort {
  port: number
  protocol: string
  state: string
}

interface ProcessDetail {
  pid: number
  name: string
  exe: string
  cmdline: string[]
  username: string
  status: string
  create_time: number | null
  cpu_pct: number
  mem_mb: number
  mem_pct: number
  parent: { pid: number; name: string } | null
  children: ProcessNode[]
  ports: ProcessPort[]
  connections_count: number
}

interface HistoryPoint {
  ts: string
  cpu_pct: number
  mem_mb: number
}

interface TreeRow {
  pid: number
  name: string
  depth: number
  current: boolean
}

const props = defineProps<{ pid: number | null }>()
const emit = defineEmits<{ close: [] }>()

const detail = ref<ProcessDetail | null>(null)
const points = ref<HistoryPoint[]>([])
const loading = ref(false)
const error = ref('')

const chartEl = ref<HTMLElement | null>(null)
let uplot: uPlot | null = null
let resizeObs: ResizeObserver | null = null
let requestId = 0

const title = computed(() => detail.value?.name || 'Process')

const treeRows = computed<TreeRow[]>(() => {
  const d = detail.value
  if (!d) return []
  const rows: TreeRow[] = []
  if (d.parent) rows.push({ pid: d.parent.pid, name: d.parent.name, depth: 0, current: false })
  rows.push({ pid: d.pid, name: d.name, depth: d.parent ? 1 : 0, current: true })
  collectNodes(d.children, d.parent ? 2 : 1, rows)
  return rows
})

function collectNodes(nodes: ProcessNode[], depth: number, out: TreeRow[]): void {
  for (const node of nodes) {
    out.push({ pid: node.pid, name: node.name, depth, current: false })
    collectNodes(node.children, depth + 1, out)
  }
}

function fmtTime(ts: number | null): string {
  if (ts == null) return '-'
  return new Date(ts * 1000).toLocaleString()
}

async function load(pid: number): Promise<void> {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const [detailResp, historyResp] = await Promise.all([
      fetch(`/api/processes/${pid}`),
      fetch(`/api/processes/${pid}/history?limit=60`),
    ])
    if (id !== requestId) return
    if (!detailResp.ok) {
      throw new Error(detailResp.status === 404
        ? 'Process not found — it may have exited.'
        : `HTTP ${detailResp.status}`)
    }
    detail.value = await detailResp.json() as ProcessDetail
    points.value = historyResp.ok ? await historyResp.json() as HistoryPoint[] : []
  } catch (err: any) {
    if (id !== requestId) return
    error.value = String(err?.message ?? err)
    detail.value = null
    points.value = []
  } finally {
    if (id === requestId) loading.value = false
  }
}

function destroyChart(): void {
  if (resizeObs) {
    resizeObs.disconnect()
    resizeObs = null
  }
  if (uplot) {
    uplot.destroy()
    uplot = null
  }
}

function renderChart(): void {
  destroyChart()
  const el = chartEl.value
  if (!el || !points.value.length) return

  const css = getComputedStyle(document.documentElement)
  const cBorder = css.getPropertyValue('--border').trim() || '#2d2f55'
  const cMuted = css.getPropertyValue('--muted').trim() || '#a0a0c0'
  const axisStyle = {
    stroke: cMuted,
    grid: { stroke: cBorder, width: 0.5 },
    ticks: { stroke: cBorder, width: 0.5 },
    font: '11px ui-monospace, monospace',
  }

  const xs = points.value.map(p => Date.parse(p.ts) / 1000)
  const cpus = points.value.map(p => p.cpu_pct)
  const mems = points.value.map(p => p.mem_mb)

  const opts: uPlot.Options = {
    width: el.clientWidth || 500,
    height: 180,
    series: [
      {},
      { label: 'CPU %', stroke: '#4fc3f7', width: 1.6, scale: 'cpu', spanGaps: true },
      { label: 'RAM MB', stroke: '#aed581', width: 1.6, scale: 'ram', spanGaps: true },
    ],
    axes: [
      { ...axisStyle },
      { ...axisStyle, scale: 'cpu' },
      { ...axisStyle, scale: 'ram', side: 1 },
    ],
    scales: {
      x: { time: true },
      cpu: { auto: true },
      ram: { auto: true },
    },
    legend: { show: true, live: false },
    cursor: { points: { show: false } },
  }

  uplot = new uPlot(opts, [xs, cpus, mems], el)
  resizeObs = new ResizeObserver(() => {
    if (uplot && chartEl.value) {
      uplot.setSize({ width: chartEl.value.clientWidth || 500, height: 180 })
    }
  })
  resizeObs.observe(el)
}

function onKeydown(evt: KeyboardEvent): void {
  if (evt.key === 'Escape' && props.pid !== null) emit('close')
}

watch(() => props.pid, (pid) => {
  if (pid === null) {
    detail.value = null
    points.value = []
    error.value = ''
    destroyChart()
    return
  }
  void load(pid)
}, { immediate: true })

watch(points, () => {
  void nextTick(() => renderChart())
})

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  destroyChart()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="pid !== null" class="overlay" @click.self="emit('close')">
      <aside class="panel" role="dialog" aria-modal="true" :aria-label="`Process ${pid}`">
        <header class="head">
          <div class="head-text">
            <h3>{{ title }} <span class="pid">#{{ pid }}</span></h3>
            <p v-if="detail" class="muted small exe" :title="detail.exe">{{ detail.exe || '(no path)' }}</p>
          </div>
          <button class="close" aria-label="Close" @click="emit('close')">×</button>
        </header>

        <p v-if="loading" class="muted">Loading…</p>
        <p v-else-if="error" class="err">{{ error }}</p>

        <template v-else-if="detail">
          <section class="block">
            <h4>Overview</h4>
            <dl class="meta">
              <dt>User</dt><dd>{{ detail.username || '-' }}</dd>
              <dt>Status</dt><dd>{{ detail.status }}</dd>
              <dt>Started</dt><dd>{{ fmtTime(detail.create_time) }}</dd>
              <dt>CPU</dt><dd>{{ detail.cpu_pct.toFixed(1) }}%</dd>
              <dt>RAM</dt><dd>{{ detail.mem_mb.toFixed(1) }} MB ({{ detail.mem_pct.toFixed(1) }}%)</dd>
              <dt>Connections</dt><dd>{{ detail.connections_count }}</dd>
              <dt>Cmdline</dt><dd class="cmdline">{{ detail.cmdline.join(' ') || '-' }}</dd>
            </dl>
          </section>

          <section class="block">
            <h4>Process Tree</h4>
            <ul class="tree">
              <li
                v-for="row in treeRows"
                :key="`${row.depth}-${row.pid}`"
                :class="{ current: row.current }"
                :style="{ paddingLeft: `${row.depth * 18}px` }"
              >
                <span v-if="row.depth" class="branch">└</span>
                <span class="pname">{{ row.name }}</span>
                <span class="muted small pid-tag">{{ row.pid }}</span>
              </li>
            </ul>
            <p v-if="treeRows.length <= 1" class="muted small">No parent or child processes.</p>
          </section>

          <section class="block">
            <h4>Listening Ports</h4>
            <table v-if="detail.ports.length" class="ports">
              <thead>
                <tr><th>Port</th><th>Protocol</th><th>State</th></tr>
              </thead>
              <tbody>
                <tr v-for="p in detail.ports" :key="`${p.port}-${p.protocol}-${p.state}`">
                  <td class="value">{{ p.port }}</td>
                  <td>{{ p.protocol }}</td>
                  <td>{{ p.state }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="muted small">No listening ports.</p>
          </section>

          <section class="block">
            <h4>CPU / RAM History <span class="muted small">(last {{ points.length }} samples)</span></h4>
            <p v-if="!points.length" class="muted small">No samples yet — collected every history tick.</p>
            <div v-show="points.length" ref="chartEl" class="chart"></div>
          </section>
        </template>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  justify-content: flex-end;
}
.panel {
  width: min(560px, 100%);
  height: 100%;
  overflow-y: auto;
  background: var(--panel, var(--bg, #1a1b2e));
  color: var(--text, #e6e6ea);
  border-left: 1px solid var(--border, #2d2f55);
  box-shadow: -12px 0 32px rgba(0, 0, 0, 0.35);
  padding: 18px 20px 28px;
}
.head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.head-text { min-width: 0; }
.head h3 { margin: 0 0 4px; }
.pid, .pid-tag { color: var(--muted, #a0a0c0); font-weight: 400; }
.exe {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 460px;
}
.close {
  background: transparent;
  color: var(--muted, #a0a0c0);
  border: 1px solid var(--border, #2d2f55);
  border-radius: 8px;
  width: 30px;
  height: 30px;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  flex: none;
}
.close:hover { color: var(--text, #e6e6ea); border-color: var(--accent, #7c9cff); }
.block { margin-top: 18px; }
.block h4 { margin: 0 0 8px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted, #a0a0c0); }
.meta { display: grid; grid-template-columns: 96px 1fr; gap: 5px 10px; margin: 0; font-size: 13px; }
.meta dt { color: var(--muted, #a0a0c0); }
.meta dd { margin: 0; word-break: break-word; }
.meta .cmdline { font-family: ui-monospace, monospace; font-size: 12px; }
.tree { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.tree li { padding: 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tree li.current { color: var(--accent, #7c9cff); font-weight: 600; }
.branch { color: var(--muted, #a0a0c0); margin-right: 6px; }
.pid-tag { margin-left: 6px; }
.ports { width: 100%; border-collapse: collapse; font-size: 13px; }
.ports th, .ports td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border, #2d2f55); }
.ports th { color: var(--muted, #a0a0c0); font-weight: 500; }
.chart { min-width: 0; margin-top: 4px; }
.muted { color: var(--muted, #a0a0c0); }
.small { font-size: 12px; }
.err { color: var(--bad, #ff6b6b); }
</style>
