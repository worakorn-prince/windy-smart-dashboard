import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import TrendsCard from '@/components/insights/TrendsCard.vue'
import { useInsightsStore } from '@/stores/insights'
import { INSIGHTS_FIXTURE } from './insights-fixtures'

const { created, MockUPlot } = vi.hoisted(() => {
  const created: Array<{ opts: Record<string, unknown>; data: Array<Array<number | null>>; destroy: ReturnType<typeof vi.fn>; setSize: ReturnType<typeof vi.fn> }> = []
  const MockUPlot = vi.fn((opts: Record<string, unknown>, data: Array<Array<number | null>>) => {
    const inst = {
      opts,
      data,
      destroy: vi.fn(),
      setSize: vi.fn(),
    }
    created.push(inst)
    return inst
  })
  ;(MockUPlot as unknown as Record<string, unknown>).sync = vi.fn()
  return { created, MockUPlot }
})

vi.mock('uplot', () => ({ default: MockUPlot }))

vi.stubGlobal('ResizeObserver', class {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
})

async function mountWithFixture() {
  setActivePinia(createPinia())
  const store = useInsightsStore()
  store.data = JSON.parse(JSON.stringify(INSIGHTS_FIXTURE))
  created.length = 0
  const wrapper = mount(TrendsCard)
  await wrapper.vm.$nextTick()
  return { wrapper, store }
}

describe('TrendsCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders uPlot with epoch-ms x axis and effective-window note (never assumes full range)', async () => {
    const { wrapper } = await mountWithFixture()
    expect(created.length).toBeGreaterThanOrEqual(1)
    const inst = created[created.length - 1]!
    const data = inst.data
    expect(data[0]).toEqual(INSIGHTS_FIXTURE.trends.points.map((p: { ts: number }) => p.ts * 1000))
    expect(data[1]).toEqual(INSIGHTS_FIXTURE.trends.points.map((p: { cpu_pct: number }) => p.cpu_pct))

    const note = wrapper.find('[data-testid="insights-window-note"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('1,200 samples')
    expect(note.text()).toContain('bucket 60s')
  })

  it('adds baseline band series (lo hidden, hi dashed fillTo=lo) on the band scale', async () => {
    await mountWithFixture()
    const inst = created[created.length - 1]!
    const series = inst.opts.series as Array<{ label?: string; scale?: string; fillTo?: number; dash?: number[] }>
    const bandSeries = series.filter(s => s.label?.includes('ช่วงปกติ'))
    expect(bandSeries).toHaveLength(2)
    expect(bandSeries[1]!.scale).toBe('%')
    expect(bandSeries[1]!.fillTo).toBe(0)
    expect(bandSeries[1]!.dash).toEqual([4, 4])
    const loSeries = series.filter(s => s.label?.includes('(ต่ำ)'))
    expect(loSeries).toHaveLength(1)
    expect(loSeries[0]!.width).toBe(0)
    expect(inst.data.some(arr => arr.every(v => v === 0))).toBe(true)
    expect(inst.data.some(arr => arr.every(v => v === 30))).toBe(true)
  })

  it('re-renders with different series and the network baseline band (lo+hi) when switching tab', async () => {
    const { wrapper } = await mountWithFixture()
    const countAfterMount = created.length
    await wrapper.find('[data-testid="insights-trend-tab-network"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(created.length).toBe(countAfterMount + 1)
    const inst = created[created.length - 1]!
    const series = inst.opts.series as Array<{ label?: string; scale?: string; fillTo?: number }>
    expect(series.some(s => s.label === 'Net ↓ MB/s')).toBe(true)
    const bandSeries = series.filter(s => s.label?.includes('ช่วงปกติ'))
    expect(bandSeries).toHaveLength(2)
    expect(bandSeries[1]!.fillTo).toBe(0)
  })

  it('destroys the chart instance on unmount', async () => {
    const { wrapper } = await mountWithFixture()
    const inst = created[created.length - 1]!
    await wrapper.unmount()
    expect(inst.destroy).toHaveBeenCalled()
  })

  it('shows empty hint and never builds a chart without points', async () => {
    setActivePinia(createPinia())
    const store = useInsightsStore()
    store.data = { ...JSON.parse(JSON.stringify(INSIGHTS_FIXTURE)), effective_window: null, trends: { range: '24h', bucket_sec: 60, count: 0, points: [] } }
    created.length = 0
    const wrapper = mount(TrendsCard)
    await wrapper.vm.$nextTick()
    expect(created).toHaveLength(0)
    expect(wrapper.find('[data-testid="insights-window-note"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('ยังไม่มีข้อมูล samples')
  })
})
