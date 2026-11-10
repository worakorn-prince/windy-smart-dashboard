import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import Viewer from '@/pages/Viewer.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [{ path: '/viewer', component: Viewer }],
})

const singleFixture = {
  generated_at: '2026-10-21T13:26:56.390808+00:00',
  kpis: {
    total_tasks: 42,
    done: 30,
    failed: 5,
    cancelled: 2,
    success_rate: 0.71,
    total_tool_calls: 100,
    recoveries: 3,
    review_fails: 1,
    tokens_total: 5000,
    open_alerts: 2,
  },
  per_task: [
    {
      task: 'FEAT-123',
      done: true,
      sessions: 2,
      tool_calls: 15,
      recovery: 1,
      review_loop: 0,
      time_to_DONE: '120.5',
      tokens: 500,
      recovery_tokens: 100,
      review_passed: 1,
      denied: 0,
    },
    {
      task: 'FEAT-456',
      done: false,
      sessions: 1,
      tool_calls: 8,
      recovery: 0,
      review_loop: 1,
      time_to_DONE: null,
      tokens: 300,
      recovery_tokens: 0,
      review_passed: 0,
      denied: 1,
    },
  ],
  timeline: [
    { time: '2026-10-21T10:00:00Z', event: 'task_started', task: 'FEAT-123' },
    { time: '2026-10-21T10:05:00Z', event: 'task_completed', task: 'FEAT-123' },
  ],
  alerts: [],
}

const allFixture = {
  ...singleFixture,
  kpis: { ...singleFixture.kpis, total_tasks: 100, done: 80 },
  per_task: [...singleFixture.per_task, { ...singleFixture.per_task[0], task: 'FEAT-789' }],
}

describe('Viewer page', () => {
  let originalFetch: typeof fetch

  beforeEach(() => {
    originalFetch = global.fetch
    vi.useFakeTimers()
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders KPIs and task names when data loads', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true, data: singleFixture }),
    })

    const wrapper = mount(Viewer, { global: { plugins: [router] } })
    await vi.runAllTimersAsync()

    expect(wrapper.find('[data-testid="viewer-kpis"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('FEAT-123')
    expect(wrapper.text()).toContain('FEAT-456')
    expect(wrapper.text()).toContain('42')
    expect(wrapper.text()).toContain('71.0%')
  })

  it('shows rebuild message when 404', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: () => Promise.resolve({
        detail: { hint: 'รัน scripts/export_json.py หรือกด Rebuild' },
      }),
    })

    const wrapper = mount(Viewer, { global: { plugins: [router] } })
    await vi.runAllTimersAsync()

    expect(wrapper.text()).toContain('ยังไม่มีข้อมูล')
    expect(wrapper.text()).toContain('Rebuild')
  })

  it('sends X-Requested-With header on rebuild', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ ok: true, data: singleFixture }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          ok: true,
          durationMs: 100,
          outputs: [{ script: 'export_json.py', code: 0, stdout_tail: '', stderr_tail: '' }],
          single: { exists: true, size: 100, modified: '2026-10-21T13:26:56.390808+00:00' },
          all: { exists: false, size: null, modified: null },
        }),
      })
    global.fetch = fetchMock

    const wrapper = mount(Viewer, { global: { plugins: [router] } })
    await vi.runAllTimersAsync()

    const rebuildBtn = wrapper.find('[data-testid="viewer-rebuild"]')
    await rebuildBtn.trigger('click')
    await vi.runAllTimersAsync()

    const rebuildCall = fetchMock.mock.calls.find((call) =>
      call[0].toString().includes('/api/viewer/rebuild')
    )
    expect(rebuildCall).toBeDefined()
    const headers = rebuildCall[1]?.headers as Record<string, string>
    expect(headers['X-Requested-With']).toBe('windy-dashboard')
  })
})