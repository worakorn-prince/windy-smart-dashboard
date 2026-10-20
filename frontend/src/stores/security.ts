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

export interface PersistedSecurityEvent {
  id: number
  ts: string
  kind: string
  source_ip: string
  detail: any
}

const MAX_EVENTS = 200

const ADMIN_TOKEN_KEY = 'dash_admin_token'

function loadAdminToken(): string {
  try {
    return sessionStorage.getItem(ADMIN_TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export const useSecurityStore = defineStore('security', () => {
  const events = ref<SecurityEvent[]>([])
  const securityEvents = ref<PersistedSecurityEvent[]>([])
  const audit = ref<AuditReport | null>(null)
  const auditRunning = ref(false)
  const suspiciousCountries = ref<string[]>([])
  const adminToken = ref<string>(loadAdminToken())

  let ws: ReturnType<typeof useWebSocket> | null = null

  function setAdminToken(token: string) {
    adminToken.value = token
    try {
      if (token) sessionStorage.setItem(ADMIN_TOKEN_KEY, token)
      else sessionStorage.removeItem(ADMIN_TOKEN_KEY)
    } catch {
      // sessionStorage unavailable (e.g. privacy mode) — keep in-memory only.
    }
  }

  function clearAdminToken() {
    setAdminToken('')
  }

  function authHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    headers['X-Admin-Token'] = adminToken.value
    return headers
  }

  async function handleActionResponse(resp: Response): Promise<any> {
    if (resp.status === 401) {
      return { ok: false, reason: 'Unauthorized (401): admin token missing or invalid — set it in Security Settings' }
    }
    if (resp.status === 403) {
      return { ok: false, reason: 'Forbidden (403): admin actions are allowed from localhost only' }
    }
    return resp.json().catch(() => ({ ok: false, reason: 'Invalid server response' }))
  }

  function connect() {
    if (ws) return
    ws = useWebSocket('/ws/security', {
      onMessage: handleMessage,
    })
  }

  function pushEvent(evt: SecurityEvent) {
    ;(evt as any).event_type = evt.type
    events.value.unshift(evt)
    if (events.value.length > MAX_EVENTS) events.value.pop()
  }

  function handleMessage(data: any) {
    if (data.type === 'hello') {
      // Server greeting.
      return
    }
    if (data.type === 'security_event') {
      // Canonical (nested) and legacy (flat) shapes are both accepted.
      const src = data.event && typeof data.event === 'object' ? data.event : data
      pushEvent({
        type: src.type ?? 'security_event',
        timestamp: src.timestamp ?? '',
        title: src.title ?? '',
        detail: src.detail ?? {},
      })
      return
    }
    // Pre-canonical backend shape: the envelope type was the event type itself
    // (e.g. "port_opened") with the fields at the top level.
    if (data.timestamp && data.title) {
      pushEvent({
        type: data.type,
        timestamp: data.timestamp,
        title: data.title,
        detail: data.detail ?? {},
      })
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

  async function loadSecurityEvents(limit = 50): Promise<{ ok: boolean; reason?: string; count?: number }> {
    try {
      const resp = await fetch(`/api/security/events?limit=${limit}`, { headers: authHeaders() })
      if (resp.status === 401 || resp.status === 403) {
        securityEvents.value = []
        return {
          ok: false,
          reason: resp.status === 401
            ? 'Unauthorized (401): admin token missing or invalid — set it in Security Settings'
            : 'Forbidden (403): event history is allowed from localhost only',
        }
      }
      const data = await resp.json()
      securityEvents.value = Array.isArray(data.events) ? data.events : []
      return { ok: true, count: securityEvents.value.length }
    } catch (err: any) {
      console.error('Failed to load security event history', err)
      return { ok: false, reason: 'Failed to load event history' }
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
      headers: authHeaders(),
      body: JSON.stringify({ pid }),
    })
    return handleActionResponse(resp)
  }

  async function blockIp(ip: string) {
    const resp = await fetch('/api/security/block', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ ip }),
    })
    return handleActionResponse(resp)
  }

  async function unblockRule(ruleName: string) {
    const resp = await fetch('/api/security/unblock', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ rule_name: ruleName }),
    })
    return handleActionResponse(resp)
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
    events, securityEvents, audit, auditRunning, suspiciousCountries, adminToken,
    connect, loadSuspicious, loadSecurityEvents, saveSuspicious, runAudit,
    setAdminToken, clearAdminToken,
    killProcess, blockIp, unblockRule, listBlocked, exportReport,
  }
})
