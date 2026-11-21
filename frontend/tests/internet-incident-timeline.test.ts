import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    isConnected: { value: false },
    send: vi.fn(),
    disconnect: vi.fn(),
  })),
}))

import IncidentTimeline from '@/components/internet/IncidentTimeline.vue'
import { useInternetStore } from '@/stores/internet'

// Deep-copy the body on every json() call: the store keeps references into the
// parsed body (e.g. state.incidents = body.incidents) and mutates them in place
// (resolve splices the list). Without a copy, one test's splice leaks into the
// shared fixture objects and breaks tests that run afterwards.
function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => JSON.parse(JSON.stringify(body)),
  } as unknown as Response
}

const ACTIVE_INCIDENT = {
  id: 'inc-001',
  started_at: 1763660000.5,
  ended_at: null,
  category: 'quality',
  severity: 'high',
  status: 'active',
  title: 'Latency spike on primary',
  summary: 'Median latency exceeded threshold',
  confidence: 0.87,
  analyzer_version: '1.0.0',
}

const ACKNOWLEDGED_INCIDENT = {
  id: 'inc-003',
  started_at: 1763659000,
  ended_at: null,
  category: 'dns',
  severity: 'medium',
  status: 'acknowledged',
  title: 'DNS latency rising',
  summary: null,
  confidence: 0.55,
  analyzer_version: '1.0.0',
}

const RESOLVED_INCIDENT = {
  id: 'inc-002',
  started_at: 1763650000,
  ended_at: 1763650600,
  category: 'route',
  severity: 'low',
  status: 'resolved',
  title: 'Route flapping on backup',
  summary: null,
  confidence: 0.6,
  analyzer_version: '1.0.0',
}

const INCIDENTS_ENVELOPE = {
  generated_at: 1763660001,
  data_window: { start: 1763659701, end: 1763660001 },
  source: 'analyzer',
  status: 'ok',
  errors: [],
  coverage: 1.0,
  incidents: [ACTIVE_INCIDENT, RESOLVED_INCIDENT, ACKNOWLEDGED_INCIDENT],
  count: 3,
}

// Backend detail shape: {**_common_metadata(), **_incident_to_dict(incident), evidence: [...]}
const DETAIL_BODY = {
  generated_at: 1763660010,
  source: 'analyzer',
  errors: [],
  coverage: 1.0,
  ...ACTIVE_INCIDENT,
  evidence: [
    {
      id: 7,
      incident_id: 'inc-001',
      evidence_type: 'latency_sample',
      observed_at: 1763660005,
      payload: { median_ms: 320, target: 'primary' },
    },
  ],
}

const RESOLVED_BODY = {
  generated_at: 1763660100,
  source: 'analyzer',
  errors: [],
  coverage: 1.0,
  ...ACTIVE_INCIDENT,
  status: 'resolved',
  ended_at: 1763660100,
}

describe('IncidentTimeline', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('fetches incidents on mount and renders rows', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, INCIDENTS_ENVELOPE)))
    const wrapper = mount(IncidentTimeline)
    await flushPromises()

    expect(wrapper.find('[data-testid="incident-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="incident-row-inc-001"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="incident-row-inc-002"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="incident-count"]').text()).toContain('3 / 3')
    expect(wrapper.text()).toContain('Latency spike on primary')
  })

  it('shows the empty state when there are no incidents', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse(200, { ...INCIDENTS_ENVELOPE, incidents: [], count: 0 }),
    ))
    const wrapper = mount(IncidentTimeline)
    await flushPromises()

    expect(wrapper.find('[data-testid="incidents-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="incident-list"]').exists()).toBe(false)
  })

  it('shows the error state with retry on fetch failure', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(500, { detail: 'boom' }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(IncidentTimeline)
    await flushPromises()

    const errorBox = wrapper.find('[data-testid="incidents-error"]')
    expect(errorBox.exists()).toBe(true)
    expect(errorBox.text()).toContain('HTTP 500')

    // retry succeeds
    fetchMock.mockImplementation(async () => jsonResponse(200, INCIDENTS_ENVELOPE))
    await wrapper.find('[data-testid="incidents-error"] .retry-btn').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="incidents-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="incident-list"]').exists()).toBe(true)
  })

  it('filters by status and category', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, INCIDENTS_ENVELOPE)))
    const wrapper = mount(IncidentTimeline)
    await flushPromises()

    await wrapper.find('[data-testid="filter-status-active"]').trigger('click')
    expect(wrapper.find('[data-testid="incident-row-inc-001"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="incident-row-inc-002"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="incident-row-inc-003"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="incident-count"]').text()).toContain('1 / 3')

    await wrapper.find('[data-testid="filter-status-all"]').trigger('click')
    await wrapper.find('[data-testid="filter-category-dns"]').trigger('click')
    expect(wrapper.find('[data-testid="incident-row-inc-001"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="incident-row-inc-003"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="incident-count"]').text()).toContain('1 / 3')

    // filter that matches nothing shows the filter-empty box
    await wrapper.find('[data-testid="filter-category-gateway"]').trigger('click')
    expect(wrapper.find('[data-testid="incidents-filter-empty"]').exists()).toBe(true)
  })

  it('expands evidence on demand', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/internet/incidents/inc-001') return jsonResponse(200, DETAIL_BODY)
      return jsonResponse(200, INCIDENTS_ENVELOPE)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(IncidentTimeline)
    await flushPromises()

    expect(wrapper.find('[data-testid="evidence-panel-inc-001"]').exists()).toBe(false)

    await wrapper.find('[data-testid="toggle-evidence-inc-001"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents/inc-001')
    const panel = wrapper.find('[data-testid="evidence-panel-inc-001"]')
    expect(panel.exists()).toBe(true)
    expect(wrapper.find('[data-testid="evidence-item-7"]').exists()).toBe(true)
    expect(panel.text()).toContain('latency_sample')
    expect(panel.text()).toContain('median_ms')

    // toggle again hides it
    await wrapper.find('[data-testid="toggle-evidence-inc-001"]').trigger('click')
    expect(wrapper.find('[data-testid="evidence-panel-inc-001"]').exists()).toBe(false)
  })

  it('resolves an active incident after confirmation', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/internet/incidents/inc-001/resolve' && init?.method === 'POST') {
        return jsonResponse(200, RESOLVED_BODY)
      }
      return jsonResponse(200, INCIDENTS_ENVELOPE)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(IncidentTimeline)
    await flushPromises()

    // resolved incidents offer no Resolve button
    expect(wrapper.find('[data-testid="resolve-inc-002"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="resolve-inc-001"]').exists()).toBe(true)

    await wrapper.find('[data-testid="resolve-inc-001"]').trigger('click')
    expect(wrapper.find('[data-testid="confirm-resolve-inc-001"]').exists()).toBe(true)

    await wrapper.find('[data-testid="confirm-no-inc-001"]').trigger('click')
    expect(wrapper.find('[data-testid="confirm-resolve-inc-001"]').exists()).toBe(false)
    expect(fetchMock).not.toHaveBeenCalledWith('/api/internet/incidents/inc-001/resolve', { method: 'POST' })

    await wrapper.find('[data-testid="resolve-inc-001"]').trigger('click')
    await wrapper.find('[data-testid="confirm-yes-inc-001"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents/inc-001/resolve', { method: 'POST' })
    // store replaced the incident in place — status badge now reads resolved
    expect(wrapper.find('[data-testid="incident-status-inc-001"]').text()).toBe('resolved')
    expect(wrapper.find('[data-testid="resolve-inc-001"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="resolve-conflict"]').exists()).toBe(false)
  })

  it('shows the conflict message when resolve returns 409', async () => {
    const conflictDetail = "cannot resolve incident in status 'resolved'"
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/internet/incidents/inc-001/resolve' && init?.method === 'POST') {
        return jsonResponse(409, { detail: conflictDetail })
      }
      return jsonResponse(200, INCIDENTS_ENVELOPE)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(IncidentTimeline)
    await flushPromises()

    await wrapper.find('[data-testid="resolve-inc-001"]').trigger('click')
    await wrapper.find('[data-testid="confirm-yes-inc-001"]').trigger('click')
    await flushPromises()

    const conflict = wrapper.find('[data-testid="resolve-conflict"]')
    expect(conflict.exists()).toBe(true)
    expect(conflict.text()).toContain(conflictDetail)
    expect(wrapper.find('[data-testid="incidents-error"]').exists()).toBe(true)
  })
})
