import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import Dashboard from '@/pages/Dashboard.vue'
import ProcessesCard from '@/components/dashboard/ProcessesCard.vue'
import ProcessDetailPanel from '@/components/dashboard/ProcessDetailPanel.vue'
import { useMetricsStore } from '@/stores/metrics'
import { CARD_DEFS, LAYOUT_STORAGE_KEY, defaultLayout, moveCard, toggleHidden } from '@/composables/useLayout'
import type { LayoutState } from '@/composables/useLayout'

vi.hoisted(() => {
  const g = globalThis as { matchMedia?: unknown; window?: { matchMedia?: unknown } }
  const matchMedia = () => ({
    matches: false,
    media: '',
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent: () => false,
  })

  const win = g.window
  if (win && typeof win.matchMedia !== 'function') {
    Object.defineProperty(win, 'matchMedia', { value: matchMedia, configurable: true, writable: true })
  }
  if (typeof g.matchMedia !== 'function') {
    Object.defineProperty(g, 'matchMedia', { value: matchMedia, configurable: true, writable: true })
  }
})

// Node 22 exposes an unusable global localStorage, so jsdom's one is missing here.
function createMemoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear() {
      data.clear()
    },
    getItem(key: string) {
      return data.has(key) ? (data.get(key) as string) : null
    },
    key(index: number) {
      return Array.from(data.keys())[index] ?? null
    },
    removeItem(key: string) {
      data.delete(key)
    },
    setItem(key: string, value: string) {
      data.set(key, String(value))
    },
  } as Storage
}

function installLocalStorage(): Storage {
  const existing = (globalThis as { localStorage?: Storage }).localStorage
  if (existing && typeof existing.getItem === 'function') return existing

  const storage = createMemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true, writable: true })
  const win = (globalThis as { window?: { localStorage?: Storage } }).window
  if (win) {
    Object.defineProperty(win, 'localStorage', { value: storage, configurable: true, writable: true })
  }
  return storage
}

const storage = installLocalStorage()

const stubs = {
  HistoryCard: {
    name: 'HistoryCard',
    template: '<div class="card">History</div>',
  },
  AlertRulesCard: {
    name: 'AlertRulesCard',
    template: '<div class="card">Alert Rules</div>',
  },
  ProcessDetailPanel: {
    name: 'ProcessDetailPanel',
    props: { pid: { type: Number, default: null } },
    emits: ['close'],
    template: '<div class="process-detail-stub" :data-pid="String(pid)" />',
  },
}

const BATTERY = {
  percent: 80,
  charging: false,
  time_remaining: null,
  health_percent: null,
  cycle_count: null,
}

const PROCESSES = [{ pid: 111, name: 'alpha', user: 'tester', cpu: 1.5, ram_percent: 2.5 }]

function mountDashboard(options: { battery?: boolean } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useMetricsStore()
  store.connect = vi.fn()
  store.loadAlertRules = vi.fn()
  store.processes = PROCESSES as never
  store.system = (options.battery === false ? null : { battery: BATTERY }) as never

  const wrapper = mount(Dashboard, { global: { plugins: [pinia], stubs, directives: { 'auto-tip': {} } } })
  return { wrapper, store }
}

function cardIds(scope: VueWrapper | ReturnType<VueWrapper['get']>): string[] {
  return scope.findAll('[data-card-id]').map((node) => node.attributes('data-card-id') ?? '')
}

function storedLayout(): LayoutState | null {
  const raw = storage.getItem(LAYOUT_STORAGE_KEY)
  return raw ? (JSON.parse(raw) as LayoutState) : null
}

beforeEach(() => {
  storage.clear()
})

describe('Dashboard layout rendering', () => {
  it('renders every card from CARD_DEFS exactly once', () => {
    const { wrapper } = mountDashboard()
    const grids = wrapper.findAll('.grid')
    const allIds = wrapper.findAll('[data-card-id]').map((node) => node.attributes('data-card-id') ?? '')

    expect(cardIds(grids[0])).toEqual(['alerts', 'alert-rules'])
    expect(cardIds(wrapper.get('[data-testid="primary-zone"]'))).toEqual(['cpu', 'ram', 'gpu'])
    expect(cardIds(wrapper.get('[data-testid="secondary-zone"]'))).toEqual([
      'power',
      'battery',
      'disk',
      'network',
      'system',
      'speedtest',
    ])
    expect(cardIds(wrapper.get('.grid.wide'))).toEqual(['history', 'processes', 'adapters'])
    expect(allIds).toHaveLength(CARD_DEFS.length)
    expect([...allIds].sort()).toEqual(CARD_DEFS.map((def) => def.id).sort())
  })

  it('hides the battery card when no battery is reported', () => {
    const { wrapper } = mountDashboard({ battery: false })

    expect(wrapper.find('[data-card-id="battery"]').exists()).toBe(false)
    expect(cardIds(wrapper.get('[data-testid="secondary-zone"]'))).toEqual([
      'power',
      'disk',
      'network',
      'system',
      'speedtest',
    ])
  })

  it('passes selectedPid to ProcessesCard and forwards select to ProcessDetailPanel', async () => {
    const { wrapper } = mountDashboard()
    const processes = wrapper.findComponent(ProcessesCard)

    expect(processes.exists()).toBe(true)
    expect(processes.props('processes')).toEqual(PROCESSES)
    expect(processes.props('selectedPid')).toBeNull()
    expect(wrapper.findComponent(ProcessDetailPanel).props('pid')).toBeNull()

    processes.vm.$emit('select', 4242)
    await nextTick()

    expect(wrapper.findComponent(ProcessesCard).props('selectedPid')).toBe(4242)
    expect(wrapper.findComponent(ProcessDetailPanel).props('pid')).toBe(4242)

    wrapper.findComponent(ProcessDetailPanel).vm.$emit('close')
    await nextTick()

    expect(wrapper.findComponent(ProcessesCard).props('selectedPid')).toBeNull()
  })

  it('renders the order and hidden cards from the saved layout', () => {
    const saved = toggleHidden(moveCard(moveCard(defaultLayout(), 'gpu', -1), 'gpu', -1), 'disk')
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(saved))

    const { wrapper } = mountDashboard()

    expect(cardIds(wrapper.get('[data-testid="primary-zone"]'))).toEqual(['gpu', 'cpu', 'ram'])
    expect(cardIds(wrapper.get('[data-testid="secondary-zone"]'))).not.toContain('disk')
  })
})

describe('Dashboard layout toolbar', () => {
  it('moves, hides, and resets cards while persisting to localStorage', async () => {
    const { wrapper } = mountDashboard()

    expect(wrapper.find('[data-testid="layout-panel"]').exists()).toBe(false)
    await wrapper.get('[data-testid="layout-toggle"]').trigger('click')
    expect(wrapper.findAll('[data-testid^="layout-row-"]')).toHaveLength(CARD_DEFS.length)

    await wrapper.get('[data-testid="layout-down-cpu"]').trigger('click')
    await nextTick()

    expect(cardIds(wrapper.get('[data-testid="primary-zone"]'))).toEqual(['ram', 'cpu', 'gpu'])
    expect(storedLayout()?.order.indexOf('cpu')).toBe(defaultLayout().order.indexOf('cpu') + 1)

    await wrapper.get('[data-testid="layout-hide-gpu"]').trigger('click')
    await nextTick()

    expect(cardIds(wrapper.get('[data-testid="primary-zone"]'))).toEqual(['ram', 'cpu'])
    expect(storedLayout()?.hidden).toContain('gpu')
    expect(wrapper.get('[data-testid="layout-hide-gpu"]').text()).toBe('Show')

    await wrapper.get('[data-testid="layout-hide-gpu"]').trigger('click')
    await nextTick()

    expect(cardIds(wrapper.get('[data-testid="primary-zone"]'))).toEqual(['ram', 'cpu', 'gpu'])
    expect(storedLayout()?.hidden).not.toContain('gpu')

    await wrapper.get('[data-testid="layout-reset"]').trigger('click')
    await nextTick()

    expect(cardIds(wrapper.get('[data-testid="primary-zone"]'))).toEqual(['cpu', 'ram', 'gpu'])
    expect(storedLayout()).toEqual(defaultLayout())
  })

  it('allows hiding the optional battery card and refuses to empty a zone', async () => {
    const { wrapper } = mountDashboard()
    await wrapper.get('[data-testid="layout-toggle"]').trigger('click')

    await wrapper.get('[data-testid="layout-hide-battery"]').trigger('click')
    await nextTick()

    expect(wrapper.find('[data-card-id="battery"]').exists()).toBe(false)
    expect(storedLayout()?.hidden).toContain('battery')

    for (const id of ['power', 'disk', 'network', 'system']) {
      await wrapper.get(`[data-testid="layout-hide-${id}"]`).trigger('click')
      await nextTick()
    }

    expect(cardIds(wrapper.get('[data-testid="secondary-zone"]'))).toEqual(['speedtest'])

    await wrapper.get('[data-testid="layout-hide-speedtest"]').trigger('click')
    await nextTick()

    expect(cardIds(wrapper.get('[data-testid="secondary-zone"]'))).toEqual(['speedtest'])
    expect(storedLayout()?.hidden).not.toContain('speedtest')
  })
})
