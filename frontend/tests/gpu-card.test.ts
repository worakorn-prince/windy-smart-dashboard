import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import GpuCard from '@/components/dashboard/GpuCard.vue'
import type { GpuSnapshot } from '@/stores/metrics'

function mountCard(gpu: GpuSnapshot | null) {
  return mount(GpuCard, {
    props: { gpu },
    global: { directives: { 'auto-tip': {} } },
  })
}

describe('GpuCard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders usage, vram percent, clocks, temp and power', () => {
    const wrapper = mountCard({
      count: 1,
      gpus: [
        {
          vendor: 'NVIDIA',
          name: 'GeForce RTX 4070',
          gpu_usage_percent: 42,
          vram_used_mb: 2048,
          vram_total_mb: 8192,
          vram_free_mb: 6144,
          graphics_clock_mhz: 1800,
          memory_clock_mhz: 7000,
          temperature_celsius: 60,
          power_draw_watts: 120,
        },
      ],
    })

    const text = wrapper.text()
    expect(text).toContain('42')
    expect(wrapper.get('[data-testid="gpu-vram-pct"]').text()).toBe('25.0%')
    expect(wrapper.get('[data-testid="gpu-clocks"]').text()).toBe('1800 / 7000 MHz')
    expect(text).toContain('60°C')
    expect(text).toContain('120 W')
    expect(text).toContain('6.0 GB')
  })

  it('prefers vram_usage_percent when the backend provides it', () => {
    const wrapper = mountCard({
      count: 1,
      gpus: [
        {
          vendor: 'NVIDIA',
          name: 'GeForce RTX 4070',
          gpu_usage_percent: 30,
          vram_used_mb: 2048,
          vram_total_mb: 8192,
          vram_usage_percent: 31.5,
        },
      ],
    })

    expect(wrapper.get('[data-testid="gpu-vram-pct"]').text()).toBe('31.5%')
  })

  it('shows an em dash for missing clocks without crashing', () => {
    const wrapper = mountCard({
      count: 1,
      gpus: [
        {
          vendor: 'Intel',
          name: 'UHD Graphics 770',
          gpu_usage_percent: 5,
          graphics_clock_mhz: null,
          memory_clock_mhz: null,
        },
      ],
    })

    expect(wrapper.get('[data-testid="gpu-clocks"]').text()).toBe('—')
  })

  it('shows the empty state when gpu is null', () => {
    const wrapper = mountCard(null)

    expect(wrapper.text()).toContain('No dedicated GPU detected')
    expect(wrapper.find('[data-testid="gpu-clocks"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="gpu-vram-pct"]').exists()).toBe(false)
  })
})
