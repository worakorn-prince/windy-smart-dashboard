import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import StatRow from '@/components/dashboard/StatRow.vue'
import { useMetricsStore } from '@/stores/metrics'

let wrapper: VueWrapper | null = null

const GB = 1024 ** 3

function mountStatRow() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useMetricsStore()
  wrapper = mount(StatRow, { global: { plugins: [pinia] } })
  return { wrapper, store }
}

function tileValue(w: VueWrapper, label: string): string {
  return w.get(`[data-testid="stat-tile-${label}"] .stat-value`).text()
}

function tileUnit(w: VueWrapper, label: string): string | null {
  const unit = w.find(`[data-testid="stat-tile-${label}"] .stat-unit`)
  return unit.exists() ? unit.text() : null
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
})

describe('StatRow', () => {
  it('renders four KPI tiles for cpu, gpu, ram and power', async () => {
    const { wrapper: w, store } = mountStatRow()

    store.cpu = { overall: 68.4, power_watts: 89 } as never
    store.ram = { used: 24.03 * GB, total: 32 * GB, percent: 75 } as never
    store.gpu = { gpus: [{ gpu_usage_percent: 42, power_draw_watts: 120 }] } as never
    store.cpuHistory = [48, 56, 62, 68.4]
    store.ramHistory = [68, 72, 75]
    await nextTick()

    for (const label of ['cpu', 'gpu', 'ram', 'power']) {
      expect(w.find(`[data-testid="stat-tile-${label}"]`).exists()).toBe(true)
    }
  })

  it('formats values and units from the metrics store', async () => {
    const { wrapper: w, store } = mountStatRow()

    store.cpu = { overall: 68.4, power_watts: 89 } as never
    store.ram = { used: 24.03 * GB, total: 32 * GB, percent: 75 } as never
    store.gpu = { gpus: [{ gpu_usage_percent: 42, power_draw_watts: 120 }] } as never
    store.cpuHistory = [48, 56, 62, 68.4]
    store.ramHistory = [68, 72, 75]
    await nextTick()

    expect(tileValue(w, 'cpu')).toBe('68')
    expect(tileUnit(w, 'cpu')).toBe('%')

    expect(tileValue(w, 'gpu')).toBe('42')
    expect(tileUnit(w, 'gpu')).toBe('%')

    expect(tileValue(w, 'ram')).toBe('24.0')
    expect(tileUnit(w, 'ram')).toBe('GB')
    // bytes from the store must be rendered as GB, not raw bytes
    expect(w.get('[data-testid="stat-tile-ram"]').text()).toContain('จากทั้งหมด 32.0 GB')

    expect(tileValue(w, 'power')).toBe('209')
    expect(tileUnit(w, 'power')).toBe('W')
  })

  it('renders the sparkline svg when history has enough samples', async () => {
    const { wrapper: w, store } = mountStatRow()

    store.cpu = { overall: 68.4, power_watts: 89 } as never
    store.cpuHistory = [48, 56, 62, 68.4]
    await nextTick()

    const cpuTile = w.get('[data-testid="stat-tile-cpu"]')
    expect(cpuTile.find('svg.stat-spark').exists()).toBe(true)
    expect(cpuTile.find('svg.stat-spark polyline').exists()).toBe(true)
    expect(cpuTile.find('svg.stat-spark polygon').exists()).toBe(true)
  })

  it('shows the collecting caption', async () => {
    const { wrapper: w, store } = mountStatRow()

    store.cpu = { overall: 20 } as never
    store.cpuHistory = [18, 20]
    await nextTick()

    expect(w.get('[data-testid="stat-tile-cpu"]').text()).toContain('อัปเดตล่าสุด')
  })

  it('shows an em dash without units when the store is empty', async () => {
    const { wrapper: w } = mountStatRow()

    for (const label of ['cpu', 'gpu', 'ram', 'power']) {
      expect(tileValue(w, label)).toBe('—')
      expect(tileUnit(w, label)).toBeNull()
    }
  })
})
