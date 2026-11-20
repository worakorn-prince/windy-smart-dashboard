import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Polyfills for jsdom
vi.hoisted(() => {
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
  globalThis.ResizeObserver = vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }))
})

import RouteTable from '@/components/internet/RouteTable.vue'
import TracerouteView from '@/components/internet/TracerouteView.vue'
import RouteHistoryChart from '@/components/internet/RouteHistoryChart.vue'
import InternetRouting from '@/pages/InternetRouting.vue'
import { useInternetStore } from '@/stores/internet'

function createStoreWithData(overrides: Partial<ReturnType<typeof useInternetStore>> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInternetStore()
  store.routes = overrides.routes ?? null
  store.traceroute = overrides.traceroute ?? null
  store.routesHistory = overrides.routesHistory ?? null
  store.loading = overrides.loading ?? false
  store.error = overrides.error ?? null
  return store
}

const MOCK_ROUTES = {
  routes: [
    { destination: '0.0.0.0', prefix_length: 0, next_hop: '192.168.1.1', interface_index: 12, metric: 25, protocol: 2, age: 3600, origin: 1, is_default: true },
    { destination: '192.168.1.0', prefix_length: 24, next_hop: null, interface_index: 12, metric: 25, protocol: 2, age: 3600, origin: 1, is_default: false },
    { destination: '10.0.0.0', prefix_length: 8, next_hop: '10.0.0.1', interface_index: 13, metric: 10, protocol: 12, age: 1800, origin: 3, is_default: false },
  ],
  default_gateway: '192.168.1.1',
  gateway_interface_index: 12,
  snapshot_ts: Date.now() / 1000,
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 300, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const MOCK_TRACEROUTE = {
  session_id: 'tr-abc123def',
  target: '8.8.8.8',
  max_hops: 30,
  protocol: 'icmp',
  hops: [
    { hop: 1, address: '192.168.1.1', rtt_ms: 1.2, status: 'success' },
    { hop: 2, address: '10.0.0.1', rtt_ms: 2.5, status: 'success' },
    { hop: 3, address: '100.64.0.1', rtt_ms: 8.3, status: 'success' },
    { hop: 4, address: null, rtt_ms: null, status: 'timeout' },
    { hop: 5, address: '8.8.8.8', rtt_ms: 12.7, status: 'success' },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 60, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const MOCK_ROUTES_HISTORY = {
  range: '1h',
  changes: [
    { timestamp: Date.now() / 1000 - 300, change_type: 'added', details: { destination: '10.10.0.0/16', next_hop: '10.10.0.1' }, severity: 'medium' },
    { timestamp: Date.now() / 1000 - 600, change_type: 'removed', details: { destination: '172.16.0.0/12' }, severity: 'high' },
    { timestamp: Date.now() / 1000 - 900, change_type: 'changed', details: { destination: '192.168.1.0/24', old_metric: 25, new_metric: 20 }, severity: 'low' },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 3600, end: Date.now() / 1000 },
  source: 'storage',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

describe('RouteTable', () => {
  beforeEach(() => {
    createStoreWithData({ routes: MOCK_ROUTES })
  })

  it('renders all routes', () => {
    const wrapper = mount(RouteTable, {
      props: {
        routes: MOCK_ROUTES.routes,
        defaultGateway: MOCK_ROUTES.default_gateway,
        gatewayInterfaceIndex: MOCK_ROUTES.gateway_interface_index,
      },
    })
    expect(wrapper.text()).toContain('default')
    expect(wrapper.text()).toContain('192.168.1.0/24')
    expect(wrapper.text()).toContain('10.0.0.0/8')
  })

  it('shows default route first', () => {
    const wrapper = mount(RouteTable, {
      props: {
        routes: MOCK_ROUTES.routes,
        defaultGateway: MOCK_ROUTES.default_gateway,
        gatewayInterfaceIndex: MOCK_ROUTES.gateway_interface_index,
      },
    })
    const rows = wrapper.findAll('tbody tr')
    expect(rows[0].text()).toContain('default')
  })

  it('renders default gateway info', () => {
    const wrapper = mount(RouteTable, {
      props: {
        routes: MOCK_ROUTES.routes,
        defaultGateway: MOCK_ROUTES.default_gateway,
        gatewayInterfaceIndex: MOCK_ROUTES.gateway_interface_index,
      },
    })
    expect(wrapper.text()).toContain('Default Gateway: 192.168.1.1')
    expect(wrapper.text()).toContain('Interface 12')
  })

  it('shows on-link for routes without next hop', () => {
    const wrapper = mount(RouteTable, {
      props: {
        routes: MOCK_ROUTES.routes,
        defaultGateway: MOCK_ROUTES.default_gateway,
        gatewayInterfaceIndex: MOCK_ROUTES.gateway_interface_index,
      },
    })
    expect(wrapper.text()).toContain('on-link')
  })

  it('shows protocol labels', () => {
    const wrapper = mount(RouteTable, {
      props: {
        routes: MOCK_ROUTES.routes,
        defaultGateway: MOCK_ROUTES.default_gateway,
        gatewayInterfaceIndex: MOCK_ROUTES.gateway_interface_index,
      },
    })
    expect(wrapper.text()).toContain('NETMGMT')
    expect(wrapper.text()).toContain('OSPF')
  })

  it('shows origin labels', () => {
    const wrapper = mount(RouteTable, {
      props: {
        routes: MOCK_ROUTES.routes,
        defaultGateway: MOCK_ROUTES.default_gateway,
        gatewayInterfaceIndex: MOCK_ROUTES.gateway_interface_index,
      },
    })
    expect(wrapper.text()).toContain('MANUAL')
    expect(wrapper.text()).toContain('DHCP')
  })

  it('shows empty state when no routes', () => {
    const wrapper = mount(RouteTable, {
      props: {
        routes: [],
        defaultGateway: null,
        gatewayInterfaceIndex: null,
      },
    })
    expect(wrapper.text()).toContain('ไม่มีเส้นทาง')
  })
})

describe('TracerouteView', () => {
  beforeEach(() => {
    createStoreWithData({ traceroute: MOCK_TRACEROUTE })
  })

  it('renders target info', () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: MOCK_TRACEROUTE.hops,
        target: MOCK_TRACEROUTE.target,
        maxHops: MOCK_TRACEROUTE.max_hops,
        protocol: MOCK_TRACEROUTE.protocol,
        sessionId: MOCK_TRACEROUTE.session_id,
      },
    })
    expect(wrapper.text()).toContain('8.8.8.8')
    expect(wrapper.text()).toContain('ICMP')
    expect(wrapper.text()).toContain('30')
  })

  it('renders all hops', () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: MOCK_TRACEROUTE.hops,
        target: MOCK_TRACEROUTE.target,
        maxHops: MOCK_TRACEROUTE.max_hops,
        protocol: MOCK_TRACEROUTE.protocol,
        sessionId: MOCK_TRACEROUTE.session_id,
      },
    })
    const rows = wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(5)
  })

  it('shows timeout for hop without address', () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: MOCK_TRACEROUTE.hops,
        target: MOCK_TRACEROUTE.target,
        maxHops: MOCK_TRACEROUTE.max_hops,
        protocol: MOCK_TRACEROUTE.protocol,
        sessionId: MOCK_TRACEROUTE.session_id,
      },
    })
    expect(wrapper.text()).toContain('*')
    expect(wrapper.text()).toContain('หมดเวลา')
  })

  it('shows RTT values', () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: MOCK_TRACEROUTE.hops,
        target: MOCK_TRACEROUTE.target,
        maxHops: MOCK_TRACEROUTE.max_hops,
        protocol: MOCK_TRACEROUTE.protocol,
        sessionId: MOCK_TRACEROUTE.session_id,
      },
    })
    expect(wrapper.text()).toContain('1.2 ms')
    expect(wrapper.text()).toContain('12.7 ms')
  })

  it('shows summary stats', () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: MOCK_TRACEROUTE.hops,
        target: MOCK_TRACEROUTE.target,
        maxHops: MOCK_TRACEROUTE.max_hops,
        protocol: MOCK_TRACEROUTE.protocol,
        sessionId: MOCK_TRACEROUTE.session_id,
      },
    })
    // Component renders "4Successful" without space between number and label
    expect(wrapper.text()).toContain('4Successful')
    expect(wrapper.text()).toContain('1Timeouts')
    expect(wrapper.text()).toContain('0Errors')
  })

  it('shows destination reached when last hop succeeds', () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: MOCK_TRACEROUTE.hops,
        target: MOCK_TRACEROUTE.target,
        maxHops: MOCK_TRACEROUTE.max_hops,
        protocol: MOCK_TRACEROUTE.protocol,
        sessionId: MOCK_TRACEROUTE.session_id,
      },
    })
    expect(wrapper.text()).toContain('Destination reached')
    expect(wrapper.text()).toContain('8.8.8.8')
  })

  it('shows incomplete when destination not reached', () => {
    const hopsWithoutDest = MOCK_TRACEROUTE.hops.slice(0, -1)
    const wrapper = mount(TracerouteView, {
      props: {
        hops: hopsWithoutDest,
        target: MOCK_TRACEROUTE.target,
        maxHops: MOCK_TRACEROUTE.max_hops,
        protocol: MOCK_TRACEROUTE.protocol,
        sessionId: MOCK_TRACEROUTE.session_id,
      },
    })
    expect(wrapper.text()).toContain('Destination not reached')
  })

  it('emits run event when button clicked', async () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: [],
        target: '8.8.8.8',
        maxHops: 30,
        protocol: 'icmp',
        sessionId: '',
      },
    })
    await wrapper.find('[data-testid="traceroute-run-btn"]').trigger('click')
    expect(wrapper.emitted('run')).toBeTruthy()
  })

  it('shows empty state when no hops', () => {
    const wrapper = mount(TracerouteView, {
      props: {
        hops: [],
        target: '8.8.8.8',
        maxHops: 30,
        protocol: 'icmp',
        sessionId: '',
      },
    })
    expect(wrapper.text()).toContain('No traceroute data')
  })
})

describe('RouteHistoryChart', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    createStoreWithData({ routesHistory: MOCK_ROUTES_HISTORY, loading: false, error: null })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders chart title', () => {
    const wrapper = mount(RouteHistoryChart)
    expect(wrapper.text()).toContain('Route Changes Over Time')
  })

  it('shows loading state', () => {
    createStoreWithData({ loading: true, routesHistory: { ...MOCK_ROUTES_HISTORY, changes: [] } })
    const wrapper = mount(RouteHistoryChart)
    expect(wrapper.text()).toContain('Loading route history')
  })

  it('shows empty state when no changes', () => {
    createStoreWithData({ routesHistory: { ...MOCK_ROUTES_HISTORY, changes: [] }, loading: false })
    const wrapper = mount(RouteHistoryChart)
    expect(wrapper.text()).toContain('No route changes')
  })

  it('renders legend with change types (Thai)', () => {
    const wrapper = mount(RouteHistoryChart)
    expect(wrapper.text()).toContain('เพิ่ม')
    expect(wrapper.text()).toContain('ลบ')
    expect(wrapper.text()).toContain('เปลี่ยนแปลง')
  })

  it('renders changes list', () => {
    const wrapper = mount(RouteHistoryChart)
    const items = wrapper.findAll('[data-testid^="route-change-"]')
    expect(items).toHaveLength(3)
  })

  it('shows severity badges (Thai)', () => {
    const wrapper = mount(RouteHistoryChart)
    expect(wrapper.text()).toContain('medium')
    expect(wrapper.text()).toContain('high')
    expect(wrapper.text()).toContain('low')
  })
})

describe('InternetRouting page', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    createStoreWithData({
      routes: MOCK_ROUTES,
      traceroute: MOCK_TRACEROUTE,
      routesHistory: MOCK_ROUTES_HISTORY,
      loading: false,
      error: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders page header', () => {
    const wrapper = mount(InternetRouting)
    expect(wrapper.text()).toContain('Routing Insights')
    expect(wrapper.text()).toContain('ตารางเส้นทาง')
  })

  it('renders route table', () => {
    const wrapper = mount(InternetRouting)
    expect(wrapper.findComponent(RouteTable).exists()).toBe(true)
  })

  it('renders traceroute view', () => {
    const wrapper = mount(InternetRouting)
    expect(wrapper.findComponent(TracerouteView).exists()).toBe(true)
  })

  it('renders route history chart', () => {
    const wrapper = mount(InternetRouting)
    expect(wrapper.findComponent(RouteHistoryChart).exists()).toBe(true)
  })

  it('renders traceroute form', () => {
    const wrapper = mount(InternetRouting)
    expect(wrapper.find('[data-testid="traceroute-target-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="traceroute-max-hops-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="traceroute-protocol-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="traceroute-run-btn"]').exists()).toBe(true)
  })

  it('runs traceroute when button clicked', async () => {
    const store = useInternetStore()
    vi.spyOn(store, 'loadTraceroute').mockResolvedValue(undefined)
    const wrapper = mount(InternetRouting)
    await wrapper.find('[data-testid="traceroute-run-btn"]').trigger('click')
    expect(wrapper.findComponent(TracerouteView).emitted('run')).toBeTruthy()
  })

  it('shows loading state', () => {
    createStoreWithData({ loading: true })
    const wrapper = mount(InternetRouting)
    expect(wrapper.text()).toContain('กำลังโหลดข้อมูล Routing')
  })

  it('shows error state', () => {
    createStoreWithData({ error: 'Failed to fetch routes' })
    const wrapper = mount(InternetRouting)
    expect(wrapper.text()).toContain('Failed to fetch routes')
    expect(wrapper.text()).toContain('ลองใหม่')
  })
})
