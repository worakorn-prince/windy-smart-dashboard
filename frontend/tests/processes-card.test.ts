import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ProcessesCard from '@/components/dashboard/ProcessesCard.vue'
import { useMetricsStore, type ProcessInfo } from '@/stores/metrics'

const GB = 1024 ** 3

const PROCESSES: ProcessInfo[] = [
  { pid: 0, name: 'System Idle Process', user: 'SYSTEM', cpu: 60, ram_percent: 0.01 },
  { pid: 12, name: 'system idle process', user: 'SYSTEM', cpu: 70, ram_percent: 0.02 },
  { pid: 100, name: 'app.exe', user: 'user', cpu: 5.7, ram_percent: 25 },
  { pid: 101, name: 'helper.exe', user: 'user', cpu: 12.3, ram_percent: 50 },
]

describe('ProcessesCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('filters idle processes and renders normalized CPU, RAM and scale', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useMetricsStore()
    store.ram = { total: 16 * GB } as never
    store.processesCpuCount = 8

    const wrapper = mount(ProcessesCard, {
      props: { processes: PROCESSES },
      global: { plugins: [pinia], directives: { 'auto-tip': {} } },
    })

    expect(wrapper.text().toLowerCase()).not.toContain('system idle process')
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.get('[data-testid="process-count"]').text()).toBe('2')
    expect(wrapper.findAll('.cpu-value').map((node) => node.text())).toEqual(['5.7%', '12.3%'])
    expect(wrapper.findAll('tbody .col-ram').map((node) => node.text())).toEqual(['4.0 GB', '8.0 GB'])
    expect(wrapper.get('[data-testid="process-cpu-scale"]').text()).toBe(
      'CPU % เทียบทั้งระบบ · 1 คอร์ = 12.5%',
    )
  })
})
