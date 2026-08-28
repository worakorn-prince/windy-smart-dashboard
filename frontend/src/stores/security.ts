import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'

export interface SecurityEvent {
  type: string
  timestamp: string
  title: string
  detail: any
}

export interface AuditReport {
  generated_at: string
  duration_ms: number
  riskscore: number
  risk_label: string
  findings: any[]
  data: any
}

const MAX_EVENTS = 200

export const useSecurityStore = defineStore('security', () => {
  const events = ref<SecurityEvent[]>([])
  const audit = ref<AuditReport | null>(null)
  const auditRunning = ref(false)
  const suspiciousCountries = ref<string[]>([])

  let ws: ReturnType<typeof useWebSocket> | null = null

  function connect() {
    if (ws) return
    ws = useWebSocket('/ws/security', {
      onMessage: handleMessage,
    })
  }

  function handleMessage(data: any) {
    if (data.type === 'hello') {
      // Server greeting.
      return
    }
    if (data.type === 'security_event') {
      const evt: SecurityEvent = {
        type: data.type,
        timestamp: data.timestamp,
        title: data.title,
        detail: data.detail,
      }
      // Preserve the type field too for routing UI icons.
      ;(evt as any).event_type = data.type
      events.value.unshift(evt)
      if (events.value.length > MAX_EVENTS) events.value.pop()
    }
  }

  async function loadSuspicious() {
    try {
      const resp = await fetch('/api/security/suspicious')
      const data = await resp.json()
      suspiciousCountries.value = data.countries || []
    } catch (err) {
      console.error('Failed to load suspicious countries', err)
    }
  }

  async function saveSuspicious(countries: string[]) {
    const resp = await fetch('/api/security/suspicious', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ countries }),
    })
    const data = await resp.json()
    if (data.ok) {
      suspiciousCountries.value = data.countries
    }
    return data
  }

  async function runAudit() {
    auditRunning.value = true
    try {
      const resp = await fetch('/api/security/audit', { method: 'POST' })
      audit.value = await resp.json()
    } catch (err: any) {
      console.error('Audit failed', err)
    } finally {
      auditRunning.value = false
    }
  }

  async function killProcess(pid: number) {
    const resp = await fetch('/api/security/kill', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid }),
    })
    return resp.json()
  }

  async function blockIp(ip: string) {
    const resp = await fetch('/api/security/block', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip }),
    })
    return resp.json()
  }

  async function unblockRule(ruleName: string) {
    const resp = await fetch('/api/security/unblock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rule_name: ruleName }),
    })
    return resp.json()
  }

  async function listBlocked() {
    const resp = await fetch('/api/security/blocked')
    return resp.json()
  }

  async function exportReport(report: any, fmt: 'pdf' | 'html' | 'json') {
    const resp = await fetch('/api/security/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fmt, report }),
    })
    if (!resp.ok) {
      const error = await resp.json().catch(() => ({}))
      throw new Error(error.reason || 'Export failed')
    }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const disposition = resp.headers.get('Content-Disposition') || ''
    const m = disposition.match(/filename="([^"]+)"/)
    a.download = m ? m[1] : `audit.${fmt}`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  return {
    events, audit, auditRunning, suspiciousCountries,
    connect, loadSuspicious, saveSuspicious, runAudit,
    killProcess, blockIp, unblockRule, listBlocked, exportReport,
  }
})
