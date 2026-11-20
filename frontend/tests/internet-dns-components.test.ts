import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// Polyfills for jsdom (must be before component imports)
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

import DnsResolverCard from '@/components/internet/DnsResolverCard.vue'
import DnsHistoryChart from '@/components/internet/DnsHistoryChart.vue'
import DnsComparison from '@/components/internet/DnsComparison.vue'
import InternetDNS from '@/pages/InternetDNS.vue'
import { useInternetStore } from '@/stores/internet'

function createStoreWithData(overrides: Partial<ReturnType<typeof useInternetStore>> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useInternetStore()
  store.dns = overrides.dns ?? null
  store.dnsHistory = overrides.dnsHistory ?? null
  store.dnsCompare = overrides.dnsCompare ?? null
  store.loading = overrides.loading ?? false
  store.error = overrides.error ?? null
  return store
}

const MOCK_DNS = {
  configured_resolvers: ['1.1.1.1', '8.8.8.8'],
  resolver_health: [
    { resolver: '1.1.1.1', status: 'ok', avg_latency_ms: 15.5, success_rate: 0.99, recent_probes: 100, last_probe_at: Date.now() / 1000 },
    { resolver: '8.8.8.8', status: 'degraded', avg_latency_ms: 45.2, success_rate: 0.95, recent_probes: 100, last_probe_at: Date.now() / 1000 },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 300, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const MOCK_DNS_HISTORY = {
  range: '1h',
  step: 60,
  points: [
    { ts: Date.now() / 1000, resolver: '1.1.1.1', hostname: 'google.com', record_type: 'A', duration_ms: 15, status: 'success', answer_count: 1, error_code: null, probe_method: 'udp' },
    { ts: Date.now() / 1000 - 60, resolver: '8.8.8.8', hostname: 'google.com', record_type: 'A', duration_ms: 25, status: 'success', answer_count: 1, error_code: null, probe_method: 'udp' },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 3600, end: Date.now() / 1000 },
  source: 'storage',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

const MOCK_DNS_COMPARE = {
  hostname: 'google.com',
  record_type: 'A',
  comparison: [
    { resolver: '1.1.1.1', probe_method: 'udp', duration_ms: 12.3, status: 'success', answer_count: 1, error_code: null },
    { resolver: '8.8.8.8', probe_method: 'udp', duration_ms: 18.7, status: 'success', answer_count: 1, error_code: null },
  ],
  generated_at: Date.now() / 1000,
  data_window: { start: Date.now() / 1000 - 60, end: Date.now() / 1000 },
  source: 'collector',
  status: 'ok',
  errors: [],
  coverage: 1.0,
}

describe('DnsResolverCard', () => {
  beforeEach(() => {
    createStoreWithData({ dns: MOCK_DNS })
  })

  it('renders resolver address', () => {
    const wrapper = mount(DnsResolverCard, {
      props: { resolver: MOCK_DNS.resolver_health[0] },
    })
    expect(wrapper.text()).toContain('1.1.1.1')
  })

  it('renders status label for ok', () => {
    const wrapper = mount(DnsResolverCard, {
      props: { resolver: MOCK_DNS.resolver_health[0] },
    })
    expect(wrapper.text()).toContain('ปกติ')
  })

  it('renders status label for degraded', () => {
    const wrapper = mount(DnsResolverCard, {
      props: { resolver: MOCK_DNS.resolver_health[1] },
    })
    expect(wrapper.text()).toContain('ลดประสิทธิภาพ')
  })

  it('renders latency value', () => {
    const wrapper = mount(DnsResolverCard, {
      props: { resolver: MOCK_DNS.resolver_health[0] },
    })
    expect(wrapper.text()).toContain('15.5 ms')
  })

  it('renders success rate', () => {
    const wrapper = mount(DnsResolverCard, {
      props: { resolver: MOCK_DNS.resolver_health[0] },
    })
    expect(wrapper.text()).toContain('99.0%')
  })

  it('applies correct status class', () => {
    const wrapper = mount(DnsResolverCard, {
      props: { resolver: MOCK_DNS.resolver_health[0] },
    })
    const badge = wrapper.find('[data-testid="resolver-status-1.1.1.1"]')
    expect(badge.classes()).toContain('status-ok')
  })
})

describe('DnsHistoryChart', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    createStoreWithData({ dnsHistory: MOCK_DNS_HISTORY, loading: false, error: null })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders chart title', () => {
    const wrapper = mount(DnsHistoryChart)
    expect(wrapper.text()).toContain('DNS Latency (All Resolvers)')
  })

  it('renders chart title with resolver filter', () => {
    const wrapper = mount(DnsHistoryChart, { props: { resolver: '1.1.1.1' } })
    expect(wrapper.text()).toContain('1.1.1.1 DNS Latency')
  })

  it('shows loading state', () => {
    createStoreWithData({ loading: true, dnsHistory: { ...MOCK_DNS_HISTORY, points: [] } })
    const wrapper = mount(DnsHistoryChart)
    expect(wrapper.text()).toContain('Loading DNS history')
  })

  it('shows empty state when no data', () => {
    createStoreWithData({ dnsHistory: { ...MOCK_DNS_HISTORY, points: [] }, loading: false })
    const wrapper = mount(DnsHistoryChart)
    expect(wrapper.text()).toContain('No DNS history data')
  })
})

describe('DnsComparison', () => {
  beforeEach(() => {
    createStoreWithData({ dnsCompare: MOCK_DNS_COMPARE })
  })

  it('renders modal when modelValue is true', () => {
    const wrapper = mount(DnsComparison, {
      props: {
        modelValue: true,
        comparison: MOCK_DNS_COMPARE.comparison,
        hostname: 'google.com',
        recordType: 'A',
      },
    })
    expect(wrapper.text()).toContain('เปรียบเทียบ DNS Resolver')
    expect(wrapper.text()).toContain('google.com')
    expect(wrapper.text()).toContain('A')
  })

  it('does not render when modelValue is false', () => {
    const wrapper = mount(DnsComparison, {
      props: {
        modelValue: false,
        comparison: MOCK_DNS_COMPARE.comparison,
        hostname: 'google.com',
        recordType: 'A',
      },
    })
    expect(wrapper.find('[data-testid="dns-comparison-modal"]').exists()).toBe(false)
  })

  it('renders comparison table with all resolvers', () => {
    const wrapper = mount(DnsComparison, {
      props: {
        modelValue: true,
        comparison: MOCK_DNS_COMPARE.comparison,
        hostname: 'google.com',
        recordType: 'A',
      },
    })
    expect(wrapper.text()).toContain('1.1.1.1')
    expect(wrapper.text()).toContain('8.8.8.8')
    expect(wrapper.text()).toContain('12.3 ms')
    expect(wrapper.text()).toContain('18.7 ms')
  })

  it('highlights fastest resolver', () => {
    const wrapper = mount(DnsComparison, {
      props: {
        modelValue: true,
        comparison: MOCK_DNS_COMPARE.comparison,
        hostname: 'google.com',
        recordType: 'A',
      },
    })
    const fastestRow = wrapper.find('[data-testid="comparison-row-1.1.1.1"]')
    expect(fastestRow.classes()).toContain('fastest')
    expect(wrapper.text()).toContain('เร็วที่สุด')
  })

  it('shows timeout status correctly', () => {
    const comparisonWithTimeout = [
      ...MOCK_DNS_COMPARE.comparison,
      { resolver: '9.9.9.9', probe_method: 'udp', duration_ms: null, status: 'timeout', answer_count: 0, error_code: 'TIMEOUT' },
    ]
    const wrapper = mount(DnsComparison, {
      props: {
        modelValue: true,
        comparison: comparisonWithTimeout,
        hostname: 'google.com',
        recordType: 'A',
      },
    })
    expect(wrapper.text()).toContain('หมดเวลา')
  })

  it('emits close event when close button clicked', async () => {
    const wrapper = mount(DnsComparison, {
      props: {
        modelValue: true,
        comparison: MOCK_DNS_COMPARE.comparison,
        hostname: 'google.com',
        recordType: 'A',
      },
    })
    await wrapper.find('[data-testid="dns-comparison-close"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })
})

describe('InternetDNS page', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    createStoreWithData({
      dns: MOCK_DNS,
      dnsHistory: MOCK_DNS_HISTORY,
      dnsCompare: MOCK_DNS_COMPARE,
      loading: false,
      error: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders page header', () => {
    const wrapper = mount(InternetDNS)
    expect(wrapper.text()).toContain('DNS Insights')
    expect(wrapper.text()).toContain('ตรวจสอบสถานะ DNS Resolver')
  })

  it('renders resolver cards', () => {
    const wrapper = mount(InternetDNS)
    const cards = wrapper.findAllComponents(DnsResolverCard)
    expect(cards).toHaveLength(2)
  })

  it('renders history charts', () => {
    const wrapper = mount(InternetDNS)
    const charts = wrapper.findAllComponents(DnsHistoryChart)
    expect(charts.length).toBeGreaterThanOrEqual(1)
  })

  it('shows status summary counts', () => {
    const wrapper = mount(InternetDNS)
    expect(wrapper.text()).toContain('1 OK')
    expect(wrapper.text()).toContain('1 Degraded')
  })

  it('renders compare form', () => {
    const wrapper = mount(InternetDNS)
    expect(wrapper.find('[data-testid="dns-compare-hostname"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="dns-compare-record-type"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="dns-compare-run"]').exists()).toBe(true)
  })

  it('opens comparison modal when compare runs', async () => {
    const store = useInternetStore()
    vi.spyOn(store, 'loadDnsCompare').mockResolvedValue(undefined)
    const wrapper = mount(InternetDNS)
    await wrapper.find('[data-testid="dns-compare-run"]').trigger('click')
    expect(wrapper.findComponent(DnsComparison).props('modelValue')).toBe(true)
  })

  it('shows loading state', () => {
    createStoreWithData({ loading: true })
    const wrapper = mount(InternetDNS)
    expect(wrapper.text()).toContain('กำลังโหลดข้อมูล DNS')
  })

  it('shows error state', () => {
    createStoreWithData({ error: 'Failed to fetch DNS' })
    const wrapper = mount(InternetDNS)
    expect(wrapper.text()).toContain('Failed to fetch DNS')
    expect(wrapper.text()).toContain('ลองใหม่')
  })
})