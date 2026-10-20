import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import SettingsPanel from '@/components/security/SettingsPanel.vue'
import { useSecurityStore } from '@/stores/security'

describe('SettingsPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => ({ ok: true, countries: ['RU'] }) })),
    )
  })

  function mountPanel() {
    return mount(SettingsPanel)
  }

  it('renders both cards and the token input', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Suspicious Countries Watchlist')
    expect(wrapper.text()).toContain('Admin Token')
    const tokenInput = wrapper.find('input[type="password"]')
    expect(tokenInput.exists()).toBe(true)
  })

  it('loads suspicious countries on mount', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const store = useSecurityStore()
    expect(store.suspiciousCountries).toEqual(['RU'])
    const input = wrapper.find('input[type="text"]')
    expect((input.element as HTMLInputElement).value).toBe('RU')
  })

  it('saves the admin token via Save Token', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const store = useSecurityStore()
    const tokenInput = wrapper.find('input[type="password"]')
    await tokenInput.setValue('secret-token')
    const buttons = wrapper.findAll('button')
    const saveTokenBtn = buttons.find(b => b.text() === 'Save Token')!
    await saveTokenBtn.trigger('click')
    await flushPromises()
    expect(store.adminToken).toBe('secret-token')
    expect(sessionStorage.getItem('dash_admin_token')).toBe('secret-token')
    expect(wrapper.text()).toContain('✓ token set')
  })

  it('clears the admin token via Clear', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    const store = useSecurityStore()
    store.setAdminToken('existing')
    await flushPromises()
    const clearBtn = wrapper.findAll('button').find(b => b.text() === 'Clear')!
    await clearBtn.trigger('click')
    await flushPromises()
    expect(store.adminToken).toBe('')
    expect(sessionStorage.getItem('dash_admin_token')).toBeNull()
  })
})
