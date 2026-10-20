import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

const ADMIN_TOKEN_KEY = 'dashboard:adminToken'

export const ADMIN_TOKEN_HINT =
  'ต้องยืนยันตัวตนผู้ดูแล (HTTP 401): ตั้งค่า token ด้วย localStorage.setItem("dashboard:adminToken", "<token>") แล้วโหลดหน้าใหม่'

export interface MaintenanceSystem {
  ok?: boolean
  isAdmin?: boolean
  os?: unknown
  cpu?: unknown
  memory?: unknown
  disks?: unknown[]
  psVersion?: string
  pythonVersion?: string
  collectedAt?: string
  cached?: boolean
  servedAt?: string
  [key: string]: unknown
}

export interface DriverDevice {
  name?: string
  status?: string
  problem?: string | number | null
  version?: string
  date?: string
  [key: string]: unknown
}

export interface ScanCounts {
  total: number
  ok: number
  issues: number
}

export interface HistoryEntry {
  action?: string
  target?: string
  status?: string
  message?: string
  at?: string
  timestamp?: string
  [key: string]: unknown
}

interface HttpError extends Error {
  status?: number
  code?: string
}

function httpError(message: string, status: number, code?: string): HttpError {
  const err = new Error(message) as HttpError
  err.status = status
  err.code = code
  return err
}

function errMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message
  if (typeof err === 'string' && err) return err
  return fallback
}

function apiError(data: any, status: number): string {
  const detail = data?.detail
  if (detail && typeof detail === 'object') {
    const text = String(detail.text ?? detail.message ?? '').trim()
    const hint = String(detail.hint ?? '').trim()
    if (text && hint) return `${text} — ${hint}`
    if (text) return text
    if (hint) return hint
  }
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  const message = String(data?.message ?? data?.reason ?? '').trim()
  if (message) return message
  return `คำขอไม่สำเร็จ (HTTP ${status})`
}

function readAdminToken(): string | null {
  try {
    return localStorage.getItem(ADMIN_TOKEN_KEY)
  } catch {
    return null
  }
}

function deviceHasIssue(device: DriverDevice): boolean {
  const status = String(device.status ?? device.Status ?? '').toUpperCase()
  const problem = device.problem ?? device.problemCode ?? device.problem_code
  const problemText = problem === null || problem === undefined ? '' : String(problem)
  const statusBad = status !== '' && status !== 'OK'
  const problemBad =
    problemText !== '' &&
    problemText !== '0' &&
    problemText.toUpperCase() !== 'CM_PROB_NONE' &&
    problemText !== 'null' &&
    problemText !== 'undefined'
  return statusBad || problemBad
}

function normalizeCounts(raw: any, list: DriverDevice[]): ScanCounts {
  if (raw && typeof raw === 'object') {
    const total = Number(raw.total ?? raw.Total ?? list.length)
    const ok = Number(raw.ok ?? raw.Ok ?? 0)
    const issues = Number(raw.issues ?? raw.Issues ?? 0)
    return {
      total: Number.isFinite(total) ? total : 0,
      ok: Number.isFinite(ok) ? ok : 0,
      issues: Number.isFinite(issues) ? issues : 0,
    }
  }
  const issues = list.filter(deviceHasIssue).length
  return { total: list.length, ok: list.length - issues, issues }
}

export const useMaintenanceStore = defineStore('maintenance', () => {
  const system = ref<MaintenanceSystem | null>(null)
  const devices = ref<DriverDevice[]>([])
  const counts = ref<ScanCounts>({ total: 0, ok: 0, issues: 0 })
  const scannedAt = ref('')
  const cached = ref(false)
  const loading = ref(false)
  const scanning = ref(false)
  const error = ref('')
  const notice = ref('')
  const history = ref<HistoryEntry[]>([])
  const busy = ref<string | null>(null)

  const isAdmin = computed(() => Boolean(system.value?.isAdmin))
  const hasIssues = computed(() => (counts.value?.issues ?? 0) > 0)

  function authHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Requested-With': 'windy-dashboard',
    }
    const token = readAdminToken()
    if (token) headers['X-Admin-Token'] = token
    return headers
  }

  async function postJson<T = any>(path: string, body?: unknown): Promise<T | null> {
    const resp = await fetch(path, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body ?? {}),
    })

    const raw = await resp.text()
    let data: any = null
    if (raw) {
      try {
        data = JSON.parse(raw)
      } catch {
        data = null
      }
    }

    const code = String(data?.detail?.code ?? data?.code ?? '')

    if (resp.status === 401 || resp.status === 403) {
      throw httpError(ADMIN_TOKEN_HINT, resp.status, code || 'UNAUTHORIZED')
    }

    if (resp.status === 501 || code === 'RELAUNCH_DISABLED') {
      notice.value = apiError(data, resp.status)
      return null
    }

    if (!resp.ok) {
      throw httpError(apiError(data, resp.status), resp.status, code)
    }

    return (data ?? {}) as T
  }

  async function loadStatus() {
    loading.value = true
    error.value = ''
    try {
      const resp = await fetch('/api/maintenance/status')
      const data: any = await resp.json().catch(() => null)
      if (!resp.ok || !data) {
        throw httpError(`โหลดสถานะระบบไม่สำเร็จ (HTTP ${resp.status})`, resp.status)
      }
      const payload = (data.system ?? data.data ?? data) as MaintenanceSystem
      if (payload && typeof payload === 'object' && payload.isAdmin === undefined && data.isAdmin !== undefined) {
        payload.isAdmin = Boolean(data.isAdmin)
      }
      system.value = payload
      cached.value = Boolean(payload?.cached ?? data.cached)
      return system.value
    } catch (err) {
      error.value = errMessage(err, 'โหลดสถานะระบบไม่สำเร็จ')
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadScan(force = false) {
    scanning.value = true
    error.value = ''
    try {
      const url = force ? '/api/maintenance/scan?refresh=1' : '/api/maintenance/scan'
      const resp = await fetch(url)
      const data: any = await resp.json().catch(() => null)
      if (!resp.ok || !data) {
        throw httpError(`สแกนไดรเวอร์ไม่สำเร็จ (HTTP ${resp.status})`, resp.status)
      }
      const payload = (data.scan ?? data.data ?? data) as any
      const list = Array.isArray(payload?.devices) ? (payload.devices as DriverDevice[]) : []
      devices.value = list
      counts.value = normalizeCounts(payload?.counts, list)
      scannedAt.value = String(payload?.scannedAt ?? '')
      cached.value = Boolean(payload?.cached ?? data.cached)
      return payload
    } catch (err) {
      error.value = errMessage(err, 'สแกนไดรเวอร์ไม่สำเร็จ')
      return null
    } finally {
      scanning.value = false
    }
  }

  async function loadHistory() {
    busy.value = 'history'
    error.value = ''
    try {
      const resp = await fetch('/api/maintenance/history?limit=200', { headers: authHeaders() })
      const data: any = await resp.json().catch(() => null)

      if (resp.status === 401 || resp.status === 403) {
        throw httpError(ADMIN_TOKEN_HINT, resp.status, 'UNAUTHORIZED')
      }

      if (!resp.ok) {
        throw httpError(
          apiError(data, resp.status),
          resp.status,
          String(data?.detail?.code ?? data?.code ?? ''),
        )
      }

      const list = Array.isArray(data?.rows)
        ? data.rows
        : Array.isArray(data?.history)
          ? data.history
          : Array.isArray(data?.items)
            ? data.items
            : []
      history.value = list as HistoryEntry[]
      return history.value
    } catch (err) {
      const status = (err as HttpError)?.status
      if (status === 404 || status === 405 || status === 501) {
        history.value = []
        notice.value = 'ยังไม่มีข้อมูลประวัติจากเซิร์ฟเวอร์ (endpoint ประวัติยังไม่พร้อมใช้งาน)'
      } else {
        error.value = errMessage(err, 'โหลดประวัติไม่สำเร็จ')
      }
      return []
    } finally {
      busy.value = null
    }
  }

  async function runAction(action: string) {
    busy.value = action
    error.value = ''
    notice.value = ''
    try {
      const path = action === 'relaunch' ? '/api/maintenance/relaunch' : '/api/maintenance/action'
      const body = action === 'relaunch' ? {} : { action }
      const res = await postJson<any>(path, body)
      if (!res) return null
      notice.value = String(res.message ?? res.reason ?? `สั่งงาน "${action}" เรียบร้อย`)
      return res
    } catch (err) {
      error.value = errMessage(err, `สั่งงาน "${action}" ไม่สำเร็จ`)
      return null
    } finally {
      busy.value = null
    }
  }

  async function runClean(targets: string[]) {
    if (!targets.length) {
      error.value = 'กรุณาเลือกเป้าหมายที่ต้องการล้างอย่างน้อยหนึ่งรายการ'
      return null
    }
    busy.value = 'clean'
    error.value = ''
    notice.value = ''
    try {
      const res = await postJson<any>('/api/maintenance/clean', { targets, confirm: true })
      if (!res) return null
      notice.value = String(res.message ?? res.reason ?? `ล้างไฟล์เรียบร้อย (${targets.length} เป้าหมาย)`)
      await loadStatus()
      return res
    } catch (err) {
      error.value = errMessage(err, 'ล้างไฟล์ไม่สำเร็จ')
      return null
    } finally {
      busy.value = null
    }
  }

  async function downloadExport(kind: 'devices' | 'history', format: 'csv' | 'json') {
    busy.value = `export:${kind}:${format}`
    error.value = ''
    notice.value = ''
    try {
      const resp = await fetch('/api/maintenance/export', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ kind, format }),
      })

      if (resp.status === 401 || resp.status === 403) {
        throw httpError(ADMIN_TOKEN_HINT, resp.status, 'UNAUTHORIZED')
      }

      if (!resp.ok) {
        let message = `ดาวน์โหลดไม่สำเร็จ (HTTP ${resp.status})`
        try {
          const data: any = await resp.json()
          message = String(data?.message ?? data?.reason ?? message)
        } catch {
          // Non-JSON error body, keep the generic message.
        }
        throw httpError(message, resp.status)
      }

      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const disposition = resp.headers.get('Content-Disposition') || ''
      const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
      a.download = match ? decodeURIComponent(match[1]) : `maintenance-${kind}-${Date.now()}.${format}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      notice.value = `ดาวน์โหลด ${kind}.${format} เรียบร้อย`
      return true
    } catch (err) {
      error.value = errMessage(err, 'ดาวน์โหลดไม่สำเร็จ')
      return false
    } finally {
      busy.value = null
    }
  }

  return {
    system,
    devices,
    counts,
    scannedAt,
    cached,
    loading,
    scanning,
    error,
    notice,
    history,
    busy,
    isAdmin,
    hasIssues,
    loadStatus,
    loadScan,
    loadHistory,
    runAction,
    runClean,
    downloadExport,
  }
})
