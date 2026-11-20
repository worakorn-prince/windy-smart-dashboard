import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import InsightsPage from '@/pages/Insights.vue'
import InsightsCardShell from '@/components/insights/InsightsCardShell.vue'
import InsightsRangeTabs from '@/components/insights/InsightsRangeTabs.vue'
import DiskGrowthCard from '@/components/insights/DiskGrowthCard.vue'
import TopProcessesCard from '@/components/insights/TopProcessesCard.vue'
import MaintenanceSummaryCard from '@/components/insights/MaintenanceSummaryCard.vue'
import SecuritySummaryCard from '@/components/insights/SecuritySummaryCard.vue'
import AnomaliesCard from '@/components/insights/AnomaliesCard.vue'
import { useInsightsStore } from '@/stores/insights'
import { EMPTY_INSIGHTS_FIXTURE, INSIGHTS_FIXTURE } from './insights-fixtures'

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

vi.mock('uplot', () => ({
  default: class MockUPlot {
    destroy(): void {}
    setSize(_size: { width: number; height: number }): void {}
  },
}))

vi.stubGlobal('ResizeObserver', class {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
})

function mountPage(pinia?: Pinia) {
  return mount(InsightsPage, {
    global: { plugins: [pinia ?? createPinia()] },
  })
}

async function mountWithStore() {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (!vi.isMockFunction(globalThis.fetch)) {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => INSIGHTS_FIXTURE,
    })))
  }
  const store = useInsightsStore()
  store.data = JSON.parse(JSON.stringify(INSIGHTS_FIXTURE))
  const wrapper = mountPage(pinia)
  await flushPromises()
  return { wrapper, store }
}

describe('InsightsCardShell states', () => {
  it('shows loading, error with retry, empty and ready slot per section', async () => {
    const loading = mount(InsightsCardShell, {
      props: { title: 'T', loading: true, ready: false },
    })
    expect(loading.text()).toContain('กำลังโหลด')

    const errorWrap = mount(InsightsCardShell, {
      props: { title: 'T', error: 'HTTP 500', ready: false },
    })
    expect(errorWrap.text()).toContain('HTTP 500')
    await errorWrap.find('button.retry-btn').trigger('click')
    expect(errorWrap.emitted('retry')).toHaveLength(1)

    const empty = mount(InsightsCardShell, {
      props: { title: 'T', ready: true, empty: 'ยังไม่มีข้อมูล' },
    })
    expect(empty.text()).toContain('ยังไม่มีข้อมูล')

    const ready = mount(InsightsCardShell, {
      props: { title: 'T', ready: true },
      slots: { default: '<p data-testid="content">OK</p>' },
    })
    expect(ready.find('[data-testid="content"]').exists()).toBe(true)
  })

  it('keeps showing stale slot content while loading a new range (ready=true)', () => {
    const wrapper = mount(InsightsCardShell, {
      props: { title: 'T', loading: true, ready: true },
      slots: { default: '<p data-testid="content">OK</p>' },
    })
    expect(wrapper.find('[data-testid="content"]').exists()).toBe(true)
  })
})

describe('InsightsRangeTabs', () => {
  it('renders three ranges and emits selected range', async () => {
    const wrapper = mount(InsightsRangeTabs, { props: { modelValue: '24h' as const } })
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs).toHaveLength(3)
    await tabs[2]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')![0]).toEqual(['30d'])
    expect(tabs[0]!.classes()).toContain('active')
  })
})

describe('DiskGrowthCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders per-mount rows with delta coloring and parsed ISO timestamps', async () => {
    const { wrapper } = await mountWithStore()
    const table = wrapper.find('[data-testid="insights-disk"] table')
    expect(table.exists()).toBe(true)
    const row = table.find('tbody tr')
    expect(row.text()).toContain('C:\\')
    expect(row.text()).toContain('120.5 GB')
    expect(row.text()).toContain('+2.50 GB')
    expect(row.find('.delta-up').exists()).toBe(true)
    const lastUpdate = row.findAll('td')[7]!.text()
    expect(lastUpdate).not.toBe('—')
  })

  it('shows empty state when disk section is empty', async () => {
    const store = useInsightsStore()
    store.data = JSON.parse(JSON.stringify(EMPTY_INSIGHTS_FIXTURE))
    const wrapper = mount(DiskGrowthCard)
    expect(wrapper.text()).toContain('ยังไม่มีข้อมูล disk_samples')
  })
})

describe('TopProcessesCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders name, avg cpu and peak memory', async () => {
    const { wrapper } = await mountWithStore()
    const row = wrapper.find('[data-testid="insights-processes"] tbody tr')
    expect(row.text()).toContain('chrome.exe')
    expect(row.text()).toContain('12.34%')
    expect(row.text()).toContain('2.00 GB')
  })
})

describe('MaintenanceSummaryCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders totals and success rate from API values', async () => {
    const { wrapper } = await mountWithStore()
    const card = wrapper.find('[data-testid="insights-maintenance"]')
    expect(card.find('[data-testid="insights-maint-total"] .tile-value').text()).toBe('10')
    expect(card.find('[data-testid="insights-maint-rate"] .tile-value').text()).toBe('90.0%')
    expect(card.text()).toContain('cleanup')
  })

  it('shows dash for success_rate when null instead of dividing by zero', async () => {
    const store = useInsightsStore()
    store.data = JSON.parse(JSON.stringify(EMPTY_INSIGHTS_FIXTURE))
    const wrapper = mount(MaintenanceSummaryCard)
    expect(wrapper.find('[data-testid="insights-maint-rate"] .tile-value').text()).toBe('—')
    expect(wrapper.text()).toContain('ยังไม่มีการบันทึก action')
  })
})

describe('SecuritySummaryCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders total, kinds and top sources', async () => {
    const { wrapper } = await mountWithStore()
    const card = wrapper.find('[data-testid="insights-security"]')
    expect(card.find('[data-testid="insights-security-total"]').text()).toContain('42')
    expect(card.text()).toContain('port_open')
    expect(card.text()).toContain('192.168.1.10')
  })

  it('shows empty state when security section is empty', async () => {
    const store = useInsightsStore()
    store.data = JSON.parse(JSON.stringify(EMPTY_INSIGHTS_FIXTURE))
    const wrapper = mount(SecuritySummaryCard)
    expect(wrapper.text()).toContain('ยังไม่มี security_events')
  })
})

describe('AnomaliesCard', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders anomaly rows with direction badge and z score', async () => {
    const { wrapper } = await mountWithStore()
    const row = wrapper.find('[data-testid="insights-anomalies"] tbody tr')
    expect(row.text()).toContain('CPU %')
    expect(row.text()).toContain('4.20')
    expect(row.text()).toContain('▲ สูงกว่าปกติ')
    expect(row.find('.badge.high').exists()).toBe(true)
  })

  it('shows friendly empty state when there are no anomalies', async () => {
    const store = useInsightsStore()
    store.data = JSON.parse(JSON.stringify(EMPTY_INSIGHTS_FIXTURE))
    const wrapper = mount(AnomaliesCard)
    expect(wrapper.text()).toContain('ไม่พบ anomaly')
  })
})

describe('Insights page', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders header, range tabs and every card section with data', async () => {
    const { wrapper } = await mountWithStore()
    expect(wrapper.find('[data-testid="insights-head"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="insights-range-tabs"]').exists()).toBe(true)
    for (const id of ['insights-trends', 'insights-disk', 'insights-processes', 'insights-maintenance', 'insights-security', 'insights-anomalies']) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(true)
    }
    expect(wrapper.find('[data-testid="insights-generated"]').text()).toContain('2026-11-20 18:00:00')
  })

  it('switching range re-requests the API with the new range', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => INSIGHTS_FIXTURE,
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { wrapper } = await mountWithStore()
    await flushPromises()
    await wrapper.find('[data-testid="insights-range-7d"]').trigger('click')
    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith('/api/insights?range=7d')
    })
  })

  it('shows error banner when the API fails and cards keep retry buttons', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })))
    const wrapper = mountPage()
    await vi.waitFor(() => {
      expect(wrapper.find('.page-error').exists()).toBe(true)
    })
    expect(wrapper.text()).toContain('500')
  })
})
