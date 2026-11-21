import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'
import { useInternetStore } from '@/stores/internet'
import { useWebSocket } from '@/composables/useWebSocket'

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    isConnected: { value: false },
    send: vi.fn(),
    disconnect: vi.fn(),
  })),
}))

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
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

const RESOLVED_INCIDENT = {
  id: 'inc-002',
  started_at: 1763650000,
  ended_at: 1763650600,
  category: 'dns',
  severity: 'low',
  status: 'resolved',
  title: 'DNS resolver timeout',
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
  incidents: [ACTIVE_INCIDENT, RESOLVED_INCIDENT],
  count: 2,
}

// Backend detail shape: {**_common_metadata(), **_incident_to_dict(incident), evidence: [...]}
// → incident fields win over envelope metadata (status stays 'active').
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

describe('internet store — fetchIncidents', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.mocked(useWebSocket).mockClear()
  })

  it('unwraps the flat envelope and stores incidents', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, INCIDENTS_ENVELOPE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    const list = await store.fetchIncidents()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents')
    expect(store.incidents).toHaveLength(2)
    expect(store.incidents[0]).toMatchObject({ id: 'inc-001', status: 'active', severity: 'high' })
    expect(list).toHaveLength(2)
    expect(store.incidentsLoading).toBe(false)
    expect(store.incidentsError).toBeNull()
  })

  it('builds query string from filters', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, INCIDENTS_ENVELOPE))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.fetchIncidents({ status: 'active', category: 'quality', since: 1763660000, limit: 50 })

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents?status=active&category=quality&since=1763660000&limit=50')
  })

  it('sets incidentsError on HTTP failure', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(500, { detail: 'boom' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    const list = await store.fetchIncidents()

    expect(list).toEqual([])
    expect(store.incidents).toEqual([])
    expect(store.incidentsError).toBe('HTTP 500')
    expect(store.incidentsLoading).toBe(false)
  })

  it('sets incidentsError when envelope status is not ok', async () => {
    const degradedEnvelope = {
      ...INCIDENTS_ENVELOPE,
      status: 'degraded',
      errors: ['analyzer unavailable'],
      incidents: [],
      count: 0,
    }
    const fetchMock = vi.fn(async () => jsonResponse(200, degradedEnvelope))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.fetchIncidents()

    expect(store.incidentsError).toBe('analyzer unavailable')
  })
})

describe('internet store — fetchIncidentDetail', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.mocked(useWebSocket).mockClear()
  })

  it('splits evidence from incident fields', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, DETAIL_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    const detail = await store.fetchIncidentDetail('inc-001')

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents/inc-001')
    expect(detail).not.toBeNull()
    expect(store.activeIncident?.id).toBe('inc-001')
    expect(store.activeIncident?.title).toBe('Latency spike on primary')
    expect(store.activeIncidentEvidence).toHaveLength(1)
    expect(store.activeIncidentEvidence[0]).toMatchObject({
      id: 7,
      evidence_type: 'latency_sample',
      payload: { median_ms: 320 },
    })
    expect((store.activeIncident as unknown as Record<string, unknown>).evidence).toBeUndefined()
    expect(store.activeIncidentLoading).toBe(false)
  })

  it('tolerates a missing evidence array', async () => {
    const body = { generated_at: 1, status: 'ok', errors: [], coverage: 1.0, ...ACTIVE_INCIDENT }
    const fetchMock = vi.fn(async () => jsonResponse(200, body))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.fetchIncidentDetail('inc-001')

    expect(store.activeIncidentEvidence).toEqual([])
  })

  it('sets incidentsError on HTTP failure', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(404, { detail: 'not found' }))
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    const detail = await store.fetchIncidentDetail('missing')

    expect(detail).toBeNull()
    expect(store.incidentsError).toBe('HTTP 404')
  })
})

describe('internet store — resolveIncident', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.mocked(useWebSocket).mockClear()
  })

  it('replaces the incident in the list on success', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/internet/incidents/inc-001/resolve' && init?.method === 'POST') {
        return jsonResponse(200, RESOLVED_BODY)
      }
      if (url === '/api/internet/incidents') {
        return jsonResponse(200, INCIDENTS_ENVELOPE)
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.fetchIncidents()
    expect(store.incidents[0].status).toBe('active')

    const ok = await store.resolveIncident('inc-001')

    expect(ok).toBe(true)
    expect(store.incidents[0]).toMatchObject({ id: 'inc-001', status: 'resolved' })
    expect(store.resolveConflictMessage).toBeNull()
    expect(store.incidentsError).toBeNull()
  })

  it('on 409 stores the detail message and refetches incidents', async () => {
    const conflictDetail = "cannot resolve incident in status 'resolved'"
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/internet/incidents/inc-002/resolve' && init?.method === 'POST') {
        return jsonResponse(409, { detail: conflictDetail })
      }
      if (url === '/api/internet/incidents') {
        return jsonResponse(200, INCIDENTS_ENVELOPE)
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    const ok = await store.resolveIncident('inc-002')

    expect(ok).toBe(false)
    expect(store.resolveConflictMessage).toBe(conflictDetail)
    expect(store.incidentsError).toBe(conflictDetail)
    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents/inc-002/resolve', { method: 'POST' })
    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents')
    expect(store.incidents).toHaveLength(2)
  })

  it('on 409 refetches the active incident detail', async () => {
    const conflictDetail = "cannot resolve incident in status 'resolved'"
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/internet/incidents/inc-001/resolve' && init?.method === 'POST') {
        return jsonResponse(409, { detail: conflictDetail })
      }
      if (url === '/api/internet/incidents') {
        return jsonResponse(200, INCIDENTS_ENVELOPE)
      }
      if (url === '/api/internet/incidents/inc-001') {
        return jsonResponse(200, DETAIL_BODY)
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.fetchIncidentDetail('inc-001')
    const ok = await store.resolveIncident('inc-001')

    expect(ok).toBe(false)
    expect(store.resolveConflictMessage).toBe(conflictDetail)
    expect(store.activeIncident?.id).toBe('inc-001')
    expect(store.activeIncidentEvidence).toHaveLength(1)
  })

  it('returns false and restores state on network error', async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error('ECONNREFUSED')
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = useInternetStore()
    await store.fetchIncidents()
    const before = [...store.incidents]

    const ok = await store.resolveIncident('inc-001')

    expect(ok).toBe(false)
    expect([...store.incidents]).toEqual(before)
    expect(store.incidentsError).toBe('ECONNREFUSED')
  })
})

describe('internet store — incidents WebSocket', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    vi.mocked(useWebSocket).mockClear()
  })

  function connectAndGetOnMessage(): { store: ReturnType<typeof useInternetStore>; onMessage: (data: any) => void } {
    const store = useInternetStore()
    store.connectIncidents()
    const options = vi.mocked(useWebSocket).mock.calls.at(-1)![1]
    return { store, onMessage: options.onMessage! }
  }

  it('connects to /ws/internet with an onMessage handler', () => {
    const store = useInternetStore()
    store.connectIncidents()

    expect(useWebSocket).toHaveBeenCalledWith('/ws/internet', expect.objectContaining({ onMessage: expect.any(Function) }))
    expect(useWebSocket).toHaveBeenCalledTimes(1)
  })

  it('is idempotent — second call does not open a new socket', () => {
    const store = useInternetStore()
    store.connectIncidents()
    store.connectIncidents()

    expect(useWebSocket).toHaveBeenCalledTimes(1)
  })

  it('refetches incidents on incident_created', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, INCIDENTS_ENVELOPE))
    vi.stubGlobal('fetch', fetchMock)

    const { store, onMessage } = connectAndGetOnMessage()
    onMessage({ type: 'incident_created', ts: 1763660000, incident: ACTIVE_INCIDENT })
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents')
    expect(store.incidents).toHaveLength(2)
  })

  it('refetches incidents on incident_updated', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, INCIDENTS_ENVELOPE))
    vi.stubGlobal('fetch', fetchMock)

    const { onMessage } = connectAndGetOnMessage()
    onMessage({ type: 'incident_updated', ts: 1763660001, incident: RESOLVED_INCIDENT })
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/internet/incidents')
  })

  it('ignores unrelated message types', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, INCIDENTS_ENVELOPE))
    vi.stubGlobal('fetch', fetchMock)

    const { onMessage } = connectAndGetOnMessage()
    onMessage({ type: 'hello', ts: 1763660002 })
    await flushPromises()

    expect(fetchMock).not.toHaveBeenCalled()
  })
})

