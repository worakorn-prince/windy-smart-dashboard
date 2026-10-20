import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSecurityStore } from '@/stores/security'
import { useWebSocket } from '@/composables/useWebSocket'

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({ close: vi.fn(), send: vi.fn() })),
}))

function getOnMessage(): (data: any) => void {
  const store = useSecurityStore()
  store.connect()
  const options = vi.mocked(useWebSocket).mock.calls.at(-1)![1]
  return options.onMessage!
}

describe('security store — handleMessage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(useWebSocket).mockClear()
  })

  it('ignores hello messages', () => {
    const onMessage = getOnMessage()
    const store = useSecurityStore()
    onMessage({ type: 'hello' })
    expect(store.events).toHaveLength(0)
  })

  it('accepts the nested canonical shape', () => {
    const onMessage = getOnMessage()
    const store = useSecurityStore()
    onMessage({
      type: 'security_event',
      event: { type: 'port_opened', timestamp: 't1', title: 'Port 22 open', detail: { port: 22 } },
    })
    expect(store.events).toHaveLength(1)
    expect(store.events[0]).toMatchObject({
      type: 'port_opened',
      event_type: 'port_opened',
      timestamp: 't1',
      title: 'Port 22 open',
      detail: { port: 22 },
    })
  })

  it('accepts the flat legacy shape', () => {
    const onMessage = getOnMessage()
    const store = useSecurityStore()
    onMessage({
      type: 'security_event',
      timestamp: 't2',
      title: 'Legacy flat event',
      detail: { src: 'legacy' },
    })
    expect(store.events).toHaveLength(1)
    expect(store.events[0]).toMatchObject({
      type: 'security_event',
      event_type: 'security_event',
      timestamp: 't2',
      title: 'Legacy flat event',
      detail: { src: 'legacy' },
    })
  })

  it('accepts the pre-canonical type-override shape', () => {
    const onMessage = getOnMessage()
    const store = useSecurityStore()
    onMessage({
      type: 'port_opened',
      timestamp: 't3',
      title: 'Pre-canonical event',
      detail: { port: 443 },
    })
    expect(store.events).toHaveLength(1)
    expect(store.events[0]).toMatchObject({
      type: 'port_opened',
      event_type: 'port_opened',
      timestamp: 't3',
      title: 'Pre-canonical event',
      detail: { port: 443 },
    })
  })

  it('ignores unknown payloads without timestamp+title', () => {
    const onMessage = getOnMessage()
    const store = useSecurityStore()
    onMessage({ type: 'something_else' })
    expect(store.events).toHaveLength(0)
  })
})

describe('security store — handleActionResponse (via killProcess)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('maps 401 to a friendly failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ status: 401, json: async () => ({}) })))
    const store = useSecurityStore()
    const res = await store.killProcess(123)
    expect(res).toMatchObject({ ok: false })
    expect(String(res.reason)).toContain('401')
  })

  it('maps 403 to a friendly failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ status: 403, json: async () => ({}) })))
    const store = useSecurityStore()
    const res = await store.blockIp('1.2.3.4')
    expect(res).toMatchObject({ ok: false })
    expect(String(res.reason)).toContain('403')
  })

  it('returns the parsed body on 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ status: 200, json: async () => ({ ok: true, rule: 'r1' }) })),
    )
    const store = useSecurityStore()
    const res = await store.unblockRule('r1')
    expect(res).toEqual({ ok: true, rule: 'r1' })
  })

  it('maps a non-JSON body to a friendly failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        status: 200,
        json: async () => {
          throw new Error('Unexpected token < in JSON')
        },
      })),
    )
    const store = useSecurityStore()
    const res = await store.killProcess(1)
    expect(res).toEqual({ ok: false, reason: 'Invalid server response' })
  })
})

describe('security store — authHeaders (via fetch call args)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('sends Content-Type and X-Admin-Token with the stored token', async () => {
    const fetchMock = vi.fn(async () => ({ status: 200, json: async () => ({ ok: true }) }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useSecurityStore()
    store.setAdminToken('tok-123')
    await store.killProcess(42)
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['Content-Type']).toBe('application/json')
    expect(headers['X-Admin-Token']).toBe('tok-123')
  })

  it('sends an empty X-Admin-Token when no token is set', async () => {
    const fetchMock = vi.fn(async () => ({ status: 200, json: async () => ({ ok: true }) }))
    vi.stubGlobal('fetch', fetchMock)
    const store = useSecurityStore()
    store.clearAdminToken()
    await store.blockIp('5.6.7.8')
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const headers = init.headers as Record<string, string>
    expect(headers['X-Admin-Token']).toBe('')
  })
})
