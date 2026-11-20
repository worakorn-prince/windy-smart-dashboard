import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Polyfills for jsdom (must be before component imports)
vi.hoisted(() => {
  // matchMedia for uPlot
  Object.defineProperty(globalThis, 'matchMedia', {
    value: vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
    writable: true,
  })
  // ResizeObserver for uPlot
  globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }))
})

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import InternetOverview from '@/components/internet/InternetOverview.vue'
import QualitySummary from '@/components/internet/QualitySummary.vue'
import InternetInsights from '@/components/internet/InternetInsights.vue'
import { useInternetStore } from '@/stores/internet'

function createStoreWithData(overrides: Partial<ReturnType<typeof useInternetStore>> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInternetStore()
  store.overview = overrides.overview ?? null
  store.quality = overrides.quality ?? null
  store.interfaces = overrides.interfaces ?? null
  store.loading = overrides.loading ?? false
  store.error = overrides.error ?? null
  return store
}

const MOCK_OVERVIEW = {
  connection_status: 'connected',
  internet_quality: {
    primary: { latency_ms: { median: 15 }, loss_pct: 0 },
    secondary: { latency_ms: { median: 18 }, loss_pct: 1 },
    gateway: { latency_ms: { median: 2 }, loss_pct: 0 },
  },
  current_throughput: { send_bps: 1_000_000, recv_bps: 5_000_000, interface_id: 'eth0' },
  active_interface: { id: 'eth0', name: 'Ethernet', speed_mbps: 1000, status: 'up' },
  recent_incidents: [],
  dns_health: { configured: ['1.1.1.1'], primary_status: 'ok', secondary_status: 'unavailable' },
}

const MOCK_QUALITY = {
  targets: [
    { target_id: 'primary', latency_ms: { median: 15, min: 10, max: 50, p95: 25, count: 100, timeouts: 0 }, jitter_ms: 2.5, loss_pct: 0, status: 'success', last_probe_at: Date.now() / 1000 },
    { target_id: 'secondary', latency_ms: { median: 18, min: 12, max: 55, p95: 30, count: 100, timeouts: 1 }, jitter_ms: 3.2, loss_pct: 1, status: 'success', last_probe_at: Date.now() / 1000 },
    { target_id: 'gateway', latency_ms: { median: 2, min: 1, max: 10, p95: 5, count: 100, timeouts: 0 }, jitter_ms: 0.5, loss_pct: 0, status: 'success', last_probe_at: Date.now() / 1000 },
  ],
}

const MOCK_INTERFACES = {
  interfaces: [
    { id: 'eth0', name: 'Ethernet', type: 'Ethernet', status: 'up', speed_mbps: 1000, current_rates: { send_bps: 1_000_000, recv_bps: 5_000_000 }, errors: { in: 0, out: 0 } },
  ],
}

describe('InternetOverview', () => {
  beforeEach(() => {
    createStoreWithData({ overview: MOCK_OVERVIEW })
  })

  it('renders connection status', () => {
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('เชื่อมต่อแล้ว')
  })

  it('renders active interface name', () => {
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('Ethernet')
  })

  it('renders throughput values', () => {
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('KB/s')
  })

  it('renders latency values', () => {
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('ms')
  })

  it('renders DNS health section', () => {
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('DNS Health')
    expect(wrapper.text()).toContain('1.1.1.1')
  })

  it('shows correct accent color for connected status', () => {
    const wrapper = mount(InternetOverview)
    const statTile = wrapper.find('[data-testid="stat-connection-status"]')
    expect(statTile.attributes('data-accent')).toBe('cyan')
  })
})

describe('InternetOverview — degraded state', () => {
  it('shows degraded status with amber accent', () => {
    createStoreWithData({
      overview: { ...MOCK_OVERVIEW, connection_status: 'degraded' },
    })
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('คุณภาพลดลง')
    const statTile = wrapper.find('[data-testid="stat-connection-status"]')
    expect(statTile.attributes('data-accent')).toBe('amber')
  })
})

describe('InternetOverview — disconnected state', () => {
  it('shows disconnected status with amber accent', () => {
    createStoreWithData({
      overview: { ...MOCK_OVERVIEW, connection_status: 'disconnected' },
    })
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('ตัดการเชื่อมต่อ')
    const statTile = wrapper.find('[data-testid="stat-connection-status"]')
    expect(statTile.attributes('data-accent')).toBe('amber')
  })
})

describe('InternetOverview — incidents', () => {
  it('renders incidents section when present', () => {
    createStoreWithData({
      overview: {
        ...MOCK_OVERVIEW,
        recent_incidents: [{ id: '1', started_at: Date.now() / 1000 - 60, category: 'quality', severity: 'HIGH', title: 'Test incident' }],
      },
    })
    const wrapper = mount(InternetOverview)
    expect(wrapper.text()).toContain('Incidents ใกล้เคียง')
    expect(wrapper.text()).toContain('Test incident')
    expect(wrapper.text()).toContain('HIGH')
  })
})

describe('QualitySummary', () => {
  beforeEach(() => {
    createStoreWithData({ quality: MOCK_QUALITY })
  })

  it('renders primary target by default', () => {
    const wrapper = mount(QualitySummary)
    expect(wrapper.text()).toContain('Primary Target')
  })

  it('renders gateway target when specified', () => {
    const wrapper = mount(QualitySummary, { props: { targetId: 'gateway' } })
    expect(wrapper.text()).toContain('Gateway')
  })

  it('renders secondary target when specified', () => {
    const wrapper = mount(QualitySummary, { props: { targetId: 'secondary' } })
    expect(wrapper.text()).toContain('Secondary Target')
  })

  it('renders latency, jitter, and loss metrics', () => {
    const wrapper = mount(QualitySummary, { props: { targetId: 'primary' } })
    expect(wrapper.text()).toContain('Latency (median)')
    expect(wrapper.text()).toContain('Jitter')
    expect(wrapper.text()).toContain('Packet Loss')
  })

  it('shows correct loss accent color', () => {
    const wrapper = mount(QualitySummary, { props: { targetId: 'primary' } })
    const lossTile = wrapper.find('[data-testid="stat-packet-loss"]')
    expect(lossTile.attributes('data-accent')).toBe('cyan')
  })

  it('shows amber accent for secondary target with 1% loss', () => {
    const wrapper = mount(QualitySummary, { props: { targetId: 'secondary' } })
    const lossTile = wrapper.find('[data-testid="stat-packet-loss"]')
    expect(lossTile.attributes('data-accent')).toBe('amber')
  })
})

describe('QualitySummary — no data', () => {
  it('shows empty state when no quality data', () => {
    createStoreWithData({ quality: { targets: [], generated_at: 0, data_window: { start: 0, end: 0 }, source: '', status: '', errors: [], coverage: 0 } })
    const wrapper = mount(QualitySummary, { props: { targetId: 'primary' } })
    expect(wrapper.text()).toContain('No quality data available')
  })
})

describe('InternetInsights', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    createStoreWithData({
      overview: MOCK_OVERVIEW,
      quality: MOCK_QUALITY,
      interfaces: MOCK_INTERFACES,
      loading: false,
      error: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders page header', () => {
    const wrapper = mount(InternetInsights)
    expect(wrapper.text()).toContain('Internet Insights')
    expect(wrapper.text()).toContain('ภาพรวมคุณภาพการเชื่อมต่ออินเทอร์เน็ต')
  })

  it('renders InternetOverview component', () => {
    const wrapper = mount(InternetInsights)
    expect(wrapper.findComponent(InternetOverview).exists()).toBe(true)
  })

  it('renders QualitySummary for all three targets', () => {
    const wrapper = mount(InternetInsights)
    const qualitySummaries = wrapper.findAllComponents(QualitySummary)
    expect(qualitySummaries).toHaveLength(3)
  })

  it('renders network interfaces table', () => {
    const wrapper = mount(InternetInsights)
    expect(wrapper.text()).toContain('Ethernet')
    expect(wrapper.text()).toContain('1000 Mbps')
  })

  it('shows loading state when loading', () => {
    createStoreWithData({ loading: true })
    const wrapper = mount(InternetInsights)
    expect(wrapper.text()).toContain('กำลังโหลดข้อมูล')
  })

  it('shows error state when error', () => {
    createStoreWithData({ error: 'Failed to fetch' })
    const wrapper = mount(InternetInsights)
    expect(wrapper.text()).toContain('Failed to fetch')
    expect(wrapper.text()).toContain('ลองใหม่')
  })
})