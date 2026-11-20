import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useInternetStore } from '@/stores/internet'
import InternetDiagnostics from '@/pages/InternetDiagnostics.vue'

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    blob: async () => new Blob([JSON.stringify(body)], { type: 'application/json' }),
  } as unknown as Response
}

const SESSION_START_FIXTURE = {
  id: 'ses-001',
  started_at: '2026-11-21T10:00:00Z',
  status: 'running',
  profile: 'standard',
  config: { profile: 'standard', duration_sec: 60 },
}

const SESSION_DONE_FIXTURE = {
  id: 'ses-001',
  started_at: '2026-11-21T10:00:00Z',
  status: 'completed',
  profile: 'standard',
  config: { profile: 'standard', duration_sec: 60 },
  summary: { findings: [] },
}

const RESULTS_FIXTURE = [
  { sequence: 1, result_type: 'probe', ts: '2026-11-21T10:00:01Z', payload: { target: '192.168.1.1', status: 'success' } },
  { sequence: 2, result_type: 'tcp_connect', ts: '2026-11-21T10:00:02Z', payload: { target: 'example.com', port: 443, status: 'success' } },
]

describe('internet store — runDiagnostic', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('posts to the tcp diagnostics endpoint and stores result', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { target: 'example.com', port: 443, status: 'success' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.runDiagnostic('tcp', { target: 'example.com', port: 443 })

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/diagnostics/tcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: 'example.com', port: 443 }),
    })
    expect(store.diagnostic).toEqual({ target: 'example.com', port: 443, status: 'success' })
    expect(store.error).toBeNull()
  })

  it('handles HTTP error from diagnostics endpoint', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(422, { detail: 'invalid target' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.runDiagnostic('mtu', { target: 'bad_target' })

    expect(store.error).toContain('422')
    expect(store.diagnostic).toBeNull()
  })
})

describe('internet store — session actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('startSession posts to /api/internet/sessions with payload', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SESSION_START_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.startSession('standard', true, ['example.com', '1.1.1.1'])

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile: 'standard',
        include_speedtest: true,
        custom_targets: ['example.com', '1.1.1.1'],
      }),
    })
    expect(store.session).toEqual(SESSION_START_FIXTURE)
  })

  it('cancelSession posts to the cancel URL and stores partial response when no session held', async () => {
    // Real backend contract: POST /sessions/{id}/cancel returns { id, status: "cancelling" }
    const fetchMock = vi.fn(async () => jsonResponse(200, { id: 'ses-001', status: 'cancelling' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.cancelSession('ses-001')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/sessions/ses-001/cancel', { method: 'POST' })
    expect(store.session?.status).toBe('cancelling')
  })

  it('cancelSession merges status into held session without dropping profile/config', async () => {
    const fetchMock = vi.fn(async (input: any) => {
      const url = typeof input === 'string' ? input : String(input)
      if (url === '/api/internet/sessions') return jsonResponse(200, SESSION_START_FIXTURE)
      return jsonResponse(200, { id: 'ses-001', status: 'cancelling' })
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.startSession('standard', false, [])
    await store.cancelSession('ses-001')

    expect(store.session?.status).toBe('cancelling')
    expect(store.session?.profile).toBe('standard')
    expect(store.session?.config).toBeDefined()
  })

  it('loadSession hits the session status URL', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, SESSION_DONE_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadSession('ses-001')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/sessions/ses-001')
    expect(store.session).toEqual(SESSION_DONE_FIXTURE)
  })

  it('loadSessionResults hits the results URL and stores rows', async () => {
    // Real backend contract: GET /sessions/{id}/results returns an envelope, not a bare array
    const fetchMock = vi.fn(async () => jsonResponse(200, { session_id: 'ses-001', status: 'completed', results: RESULTS_FIXTURE }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.loadSessionResults('ses-001')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/sessions/ses-001/results')
    expect(store.sessionResults).toEqual(RESULTS_FIXTURE)
  })

  it('exportSession fetches export?format=json and downloads via blob link', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { id: 'ses-001', results: [] }))
    vi.stubGlobal('fetch', fetchMock)
    const createObjectURL = vi.fn(() => 'blob:http://localhost/ses-001')
    const revokeObjectURL = vi.fn()
    // jsdom lacks URL.createObjectURL/revokeObjectURL — override only those methods
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }))
    const clickMock = vi.fn()
    const realCreateElement = document.createElement.bind(document)
    const appendChild = vi.spyOn(document.body, 'appendChild').mockImplementation(((node: Node) => node) as typeof document.body.appendChild)
    const removeChild = vi.spyOn(document.body, 'removeChild').mockImplementation(((node: Node) => node) as typeof document.body.removeChild)
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
      const el = realCreateElement(tag)
      if (tag === 'a') {
        Object.defineProperty(el, 'click', { value: clickMock, configurable: true })
      }
      return el
    }) as typeof document.createElement)

    const store = useInternetStore()
    await store.exportSession('ses-001', 'json')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/sessions/ses-001/export?format=json')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickMock).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:http://localhost/ses-001')
    appendChild.mockRestore()
    removeChild.mockRestore()
    createElementSpy.mockRestore()
  })
})

describe('internet store — session polling', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('poll stops calling loadSession once status is no longer running', async () => {
    vi.useFakeTimers()
    const responses = [
      jsonResponse(200, { ...SESSION_START_FIXTURE, id: 'ses-poll' }),
      jsonResponse(200, { ...SESSION_DONE_FIXTURE, id: 'ses-poll', status: 'completed' }),
      jsonResponse(200, { ...SESSION_DONE_FIXTURE, id: 'ses-poll', status: 'completed' }),
    ]
    let call = 0
    const fetchMock = vi.fn(async () => {
      const resp = responses[Math.min(call, responses.length - 1)]
      call += 1
      return resp
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.startSession('standard', false, [])
    expect(store.session?.status).toBe('running')

    // Page-level polling loop: same logic the page applies on top of the store
    const pollCallsBefore = fetchMock.mock.calls.length
    const timer = setInterval(async () => {
      await store.loadSession('ses-poll')
    }, 2000)
    // drain first tick
    await vi.advanceTimersByTimeAsync(2000)
    await Promise.resolve()
    // status became completed after first poll → next ticks should not be needed,
    // page stops the interval; simulate stop
    clearInterval(timer)
    const callsAfterFirstTick = fetchMock.mock.calls.length
    await vi.advanceTimersByTimeAsync(6000)
    expect(fetchMock.mock.calls.length).toBe(callsAfterFirstTick)

    expect(store.session?.status).toBe('completed')
    expect(pollCallsBefore).toBeGreaterThan(0)
    vi.useRealTimers()
  })

  it('page poll stops when status != running (fake timers, page flow)', async () => {
    vi.useFakeTimers()
    let pollCount = 0
    const fetchMock = vi.fn(async (input: any) => {
      const url = typeof input === 'string' ? input : String(input)
      if (url === '/api/internet/sessions' ) return jsonResponse(200, SESSION_START_FIXTURE)
      if (url === '/api/internet/sessions/ses-001') {
        pollCount += 1
        return jsonResponse(200, SESSION_DONE_FIXTURE)
      }
      return jsonResponse(200, { session_id: 'ses-001', status: 'completed', results: RESULTS_FIXTURE })
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.startSession('standard', false, [])
    expect(store.session?.status).toBe('running')

    // replicate page polling: stop when status != running
    let ticks = 0
    let elapsed = 0
    const timer = setInterval(async () => {
      elapsed += 2000
      await store.loadSession('ses-001')
      ticks += 1
      if (store.session?.status !== 'running' || elapsed >= 150000) {
        clearInterval(timer)
      }
    }, 2000)

    await vi.advanceTimersByTimeAsync(2000)
    expect(store.session?.status).toBe('completed')
    const callsAtStop = fetchMock.mock.calls.length
    expect(ticks).toBe(1)

    await vi.advanceTimersByTimeAsync(20000)
    expect(fetchMock.mock.calls.length).toBe(callsAtStop)
    clearInterval(timer)
    vi.useRealTimers()
  })
})

describe('internet diagnostics page', () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: { template: '<div />' } },
      { path: '/internet-diagnostics', name: 'internet-diagnostics', component: InternetDiagnostics },
    ],
  })

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, {})))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders all six tool tabs', async () => {
    router.push('/internet-diagnostics')
    await router.isReady()
    const wrapper = mount(InternetDiagnostics, { global: { plugins: [router] } })
    await flushPromises()

    for (const tool of ['ping', 'dns', 'tcp', 'tls', 'http', 'mtu']) {
      expect(wrapper.find(`[data-testid="diag-tab-${tool}"]`).exists()).toBe(true)
    }
    wrapper.unmount()
  })

  it('renders session controls (profile select, speedtest checkbox, start button)', async () => {
    router.push('/internet-diagnostics')
    await router.isReady()
    const wrapper = mount(InternetDiagnostics, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="session-profile-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-speedtest-checkbox"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-start-btn"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-cancel-btn"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-targets-input"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('switches tool tab and renders per-tool form fields', async () => {
    router.push('/internet-diagnostics')
    await router.isReady()
    const wrapper = mount(InternetDiagnostics, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('[data-testid="diag-tab-tcp"]').trigger('click')
    expect(wrapper.find('[data-testid="diag-port-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="diag-run-btn"]').exists()).toBe(true)

    await wrapper.find('[data-testid="diag-tab-http"]').trigger('click')
    expect(wrapper.find('[data-testid="diag-url-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="diag-follow-redirects-checkbox"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('run button calls store.runDiagnostic and shows result panel with status badge', async () => {
    router.push('/internet-diagnostics')
    await router.isReady()
    const fetchMock = vi.fn(async () => jsonResponse(200, { target: '8.8.8.8', status: 'success', duration_ms: 12.5 }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(InternetDiagnostics, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('[data-testid="diag-run-btn"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/diagnostics/ping', expect.objectContaining({ method: 'POST' }))
    expect(wrapper.find('[data-testid="diag-result-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="diag-status-badge"]').text()).toContain('success')
    wrapper.unmount()
  })

  it('start button starts session and shows results table with export buttons', async () => {
    router.push('/internet-diagnostics')
    await router.isReal?.()
    await router.isReady()
    let call = 0
    const fetchMock = vi.fn(async () => {
      call += 1
      if (call === 1) return jsonResponse(200, SESSION_START_FIXTURE)
      return jsonResponse(200, { session_id: 'ses-001', status: 'running', results: RESULTS_FIXTURE })
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(InternetDiagnostics, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('[data-testid="session-start-btn"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/sessions', expect.objectContaining({ method: 'POST' }))
    expect(wrapper.find('[data-testid="session-results-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-export-json"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-export-csv"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-export-md"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('start button sends profile, include_speedtest and custom_targets payload', async () => {
    router.push('/internet-diagnostics')
    await router.isReady()
    const fetchMock = vi.fn(async () => jsonResponse(200, SESSION_START_FIXTURE))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(InternetDiagnostics, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('[data-testid="session-profile-select"]').setValue('deep')
    await wrapper.find('[data-testid="session-speedtest-checkbox"]').setValue(true)
    await wrapper.find('[data-testid="session-targets-input"]').setValue('example.com, 1.1.1.1')
    await wrapper.find('[data-testid="session-start-btn"]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile: 'deep',
        include_speedtest: true,
        custom_targets: ['example.com', '1.1.1.1'],
      }),
    })
    wrapper.unmount()
  })
})
