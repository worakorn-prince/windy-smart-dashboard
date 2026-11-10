import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BatteryCard from '@/components/dashboard/BatteryCard.vue'
import type { BatteryInfo } from '@/stores/metrics'

function mountCard(battery: BatteryInfo | null) {
  return mount(BatteryCard, { props: { battery } })
}

describe('BatteryCard', () => {
  it('renders percent, charging status, time remaining, health and cycles', () => {
    const wrapper = mountCard({
      percent: 85,
      charging: true,
      time_remaining: 9000,
      health_percent: 92.4,
      cycle_count: 310,
    })

    expect(wrapper.get('[data-testid="battery-card"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="battery-percent"]').text()).toBe('85%')
    expect(wrapper.get('[data-testid="battery-status"]').text()).toContain('Charging')
    expect(wrapper.get('[data-testid="battery-time-remaining"]').text()).toBe('2h 30m')
    expect(wrapper.get('[data-testid="battery-health"]').text()).toBe('92.4%')
    expect(wrapper.get('[data-testid="battery-cycles"]').text()).toBe('310')
  })

  it('shows "No battery detected" and does not crash without battery', () => {
    const wrapper = mountCard(null)

    expect(wrapper.text()).toContain('Battery')
    expect(wrapper.text()).toContain('No battery detected')
    expect(wrapper.find('[data-testid="battery-percent"]').exists()).toBe(false)
  })

  it('shows an em dash when time_remaining is null', () => {
    const wrapper = mountCard({
      percent: 40,
      charging: false,
      time_remaining: null,
      health_percent: null,
      cycle_count: null,
    })

    expect(wrapper.get('[data-testid="battery-time-remaining"]').text()).toBe('—')
    expect(wrapper.get('[data-testid="battery-health"]').text()).toBe('—')
    expect(wrapper.get('[data-testid="battery-cycles"]').text()).toBe('—')
    expect(wrapper.get('[data-testid="battery-status"]').text()).toContain('battery')
  })
})
