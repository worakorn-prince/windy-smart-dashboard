import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'

export interface CpuInfo {
  Name?: string
  Manufacturer?: string
  NumberOfCores?: number
  NumberOfLogicalProcessors?: number
  MaxClockSpeed?: number
  L2CacheSize?: number
  L3CacheSize?: number
  SocketDesignation?: string
}

export interface CpuTempReading {
  name: string
  value: number
}

export interface CpuTemperature {
  primary?: number | null
  core_temps: CpuTempReading[]
  max: number
  average: number
}

export interface CpuSnapshot {
  overall: number
  cores: number[]
  core_count: number
  freq_mhz: { current: number | null; min: number | null; max: number | null }
  info?: CpuInfo | null
  temperature_celsius?: CpuTemperature | null
  power_watts?: number | null
}

export interface RamModule {
  capacity_gb: number
  speed_mhz: number | string
  type: string
  manufacturer: string
  part_number: string
  location: string
  bank: string
}

export interface RamDetails {
  type: string
  channels: number
  max_speed_mhz: number
  modules: RamModule[]
  total_capacity_gb: number
}

export interface RamSnapshot {
  total: number
  used: number
  available: number
  percent: number
  cached: number
  swap_total: number
  swap_used: number
  swap_percent: number
  details?: RamDetails | null
  temperature_celsius?: { temps: CpuTempReading[]; max: number } | null
  voltage?: number | null
}

export interface DiskPartition {
  device: string
  mountpoint: string
  fstype: string
  total: number
  used: number
  free: number
  percent: number
}

export interface DriveDetails {
  model: string
  type: string
  interface: string
  capacity_gb: number
  serial: string
  firmware: string
  status: string
  smart_health: string
  smart_raw: Record<string, any>
}

export interface DiskSnapshot {
  partitions: DiskPartition[]
  io: { read_bytes_per_sec: number; write_bytes_per_sec: number }
  details?: DriveDetails[]
  temperatures?: Record<string, number>
}

export interface AdapterInfo {
  name: string
  description: string
  mac: string
  type: string
  speed_mbps: number
  status: string
  connection_name: string
  manufacturer: string
  ipv4: string[]
  ipv6: string[]
  gateway: string[]
  dns: string[]
}

export interface WifiInfo {
  SSID: string
  Signal: number
  BSSID: string
  Channel: number
  RadioType: string
}

export interface NetworkSnapshot {
  interfaces: Record<string, string[]>
  bytes_sent: number
  bytes_recv: number
  packets_sent: number
  packets_recv: number
  send_bytes_per_sec: number
  recv_bytes_per_sec: number
  adapters?: AdapterInfo[]
  wifi?: WifiInfo | null
  public_ip?: string | null
}

export interface GpuInfo {
  vendor: string
  name: string
  driver_version?: string
  vram_total_mb?: number | null
  vram_used_mb?: number
  vram_free_mb?: number
  gpu_usage_percent?: number
  vram_usage_percent?: number
  temperature_celsius?: number
  power_draw_watts?: number | null
  graphics_clock_mhz?: number | null
  memory_clock_mhz?: number | null
  video_processor?: string
  resolution?: string
  refresh_rate?: number
  status?: string
  index?: number
}

export interface GpuSnapshot {
  gpus: GpuInfo[]
  count: number
}

export interface BatteryInfo {
  percent: number
  charging: boolean
  time_remaining: number | null
  health_percent: number | null
  cycle_count: number | null
}

export interface SystemInfo {
  hostname: string
  os: string
  os_name: string
  os_version: string
  machine: string
  processor: string
  python_version: string
  boot_time: string
  uptime_seconds: number
  uptime: string
  now: string
  battery?: BatteryInfo | null
  sensors?: { state: string; message: string } | null
}

export interface ProcessInfo {
  pid: number
  name: string
  user: string
  cpu: number
  ram_percent: number
}

export interface SpeedtestResult {
  ok: boolean
  error?: string
  download_mbps?: number
  upload_mbps?: number
  ping_ms?: number
  server?: any
  timestamp?: number
}

const MAX_HISTORY = 60

export interface AlertItem {
  id: string
  title: string
  message: string
  ts: number
  uid?: string
}

export interface AlertRule {
  id: string
  metric: string
  op: string
  threshold: number
  enabled: boolean
}

export interface WebhookChannel {
  enabled: boolean
  url: string
}

export interface LineChannel {
  enabled: boolean
  token: string
  token_set?: boolean
  target: string
}

export interface AlertChannels {
  toast: boolean
  sound: boolean
  webhook: WebhookChannel
  line: LineChannel
}

export interface AlertRulesPayload {
  rules: AlertRule[]
  channels: AlertChannels
}

export interface AlertTestResult {
  ok: boolean
  channels: Record<string, boolean>
}

export function normalizeAlertChannels(raw?: Partial<AlertChannels> | null): AlertChannels {
  return {
    toast: raw?.toast ?? true,
    sound: raw?.sound ?? false,
    webhook: { enabled: raw?.webhook?.enabled ?? false, url: raw?.webhook?.url ?? '' },
    line: {
      enabled: raw?.line?.enabled ?? false,
      token: raw?.line?.token ?? '',
      token_set: raw?.line?.token_set ?? false,
      target: raw?.line?.target ?? '',
    },
  }
}

export type SeverityLevel = 'ok' | 'warn' | 'crit'
export type SeverityKind = 'cpu' | 'ram' | 'temp' | 'gpu'

export interface SeverityThreshold {
  warn: number
  crit: number
}

export const SEVERITY_THRESHOLDS: Record<SeverityKind, SeverityThreshold> = {
  cpu: { warn: 75, crit: 90 },
  ram: { warn: 85, crit: 95 },
  temp: { warn: 75, crit: 85 },
  gpu: { warn: 75, crit: 90 },
}

export function severityOf(kind: SeverityKind, value: number | null | undefined): SeverityLevel {
  if (value === null || value === undefined || Number.isNaN(value)) return 'ok'
  const t = SEVERITY_THRESHOLDS[kind]
  if (value >= t.crit) return 'crit'
  if (value >= t.warn) return 'warn'
  return 'ok'
}

export const SEVERITY_COLORS: Record<SeverityLevel, string> = {
  ok: '#4ade80',
  warn: '#fbbf24',
  crit: '#f87171',
}

const ADMIN_TOKEN_KEY = 'dashboard:adminToken'

function jsonHeaders(withAdmin = false): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (withAdmin) {
    try {
      const token = sessionStorage.getItem(ADMIN_TOKEN_KEY)
      if (token) headers['X-Admin-Token'] = token
    } catch {
      // sessionStorage unavailable (privacy mode) — request stays unauthenticated.
    }
  }
  return headers
}

function rulesPayloadBody(payload: AlertRulesPayload): Record<string, unknown> {
  const line: Record<string, unknown> = {
    enabled: payload.channels.line.enabled,
    target: payload.channels.line.target,
  }
  // An empty field means "keep the stored token"; only a typed value is sent.
  if (payload.channels.line.token) line.token = payload.channels.line.token
  return {
    rules: payload.rules,
    channels: {
      toast: payload.channels.toast,
      sound: payload.channels.sound,
      webhook: { ...payload.channels.webhook },
      line,
    },
  }
}

export const useMetricsStore = defineStore('metrics', () => {
  const cpu = ref<CpuSnapshot | null>(null)
  const ram = ref<RamSnapshot | null>(null)
  const disk = ref<DiskSnapshot | null>(null)
  const network = ref<NetworkSnapshot | null>(null)
  const system = ref<SystemInfo | null>(null)
  const gpu = ref<GpuSnapshot | null>(null)
  const processes = ref<ProcessInfo[]>([])
  const ping = ref<{ latency_ms: number; target: string }>({ latency_ms: 0, target: '1.1.1.1' })

  const cpuHistory = ref<number[]>([])
  const ramHistory = ref<number[]>([])
  const netSendHistory = ref<number[]>([])
  const netRecvHistory = ref<number[]>([])

  const speedtest = ref<SpeedtestResult | null>(null)
  const speedtestRunning = ref(false)

  let ws: ReturnType<typeof useWebSocket> | null = null

  function connect() {
    if (ws) return
    ws = useWebSocket('/ws/metrics', {
      onMessage: handleMessage,
    })
  }

  function handleMessage(data: any) {
    if (data.type === 'metrics') {
      // Live ticks (live_snapshot) carry only a few scalars e.g. cpu:{overall},
      // ram:{percent}. Shallow-merge over the previous snapshot so detail
      // fields from the last full_snapshot (info/freq/temperature/details/...)
      // survive; missing keys keep their old values, present keys overwrite.
      if (data.cpu) cpu.value = { ...(cpu.value ?? {}), ...data.cpu } as CpuSnapshot
      if (data.ram) ram.value = { ...(ram.value ?? {}), ...data.ram } as RamSnapshot
      if (data.disk) {
        const prevIo = (disk.value as any)?.io ?? {}
        disk.value = { ...((disk.value ?? {}) as object), ...data.disk } as DiskSnapshot
        if (data.disk.io) disk.value.io = { ...prevIo, ...data.disk.io }
      }
      if (data.network) network.value = { ...(network.value ?? {}), ...data.network } as NetworkSnapshot
      if (data.gpu) gpu.value = data.gpu
      if (data.ping) ping.value = data.ping

      if (data.cpu?.overall !== undefined) {
        cpuHistory.value.push(data.cpu.overall)
        if (cpuHistory.value.length > MAX_HISTORY) cpuHistory.value.shift()
      }
      if (data.ram?.percent !== undefined) {
        ramHistory.value.push(data.ram.percent)
        if (ramHistory.value.length > MAX_HISTORY) ramHistory.value.shift()
      }
      if (data.network) {
        netSendHistory.value.push(data.network.send_bytes_per_sec)
        netRecvHistory.value.push(data.network.recv_bytes_per_sec)
        if (netSendHistory.value.length > MAX_HISTORY) netSendHistory.value.shift()
        if (netRecvHistory.value.length > MAX_HISTORY) netRecvHistory.value.shift()
      }
    } else if (data.type === 'system') {
      system.value = data.system
    } else if (data.type === 'processes') {
      processes.value = data.processes || []
    } else if (data.type === 'speedtest_result') {
      speedtest.value = data
      speedtestRunning.value = false
    } else if (data.type === 'alert') {
      pushAlert({
        id: String(data.id ?? `alert-${Date.now()}`),
        title: String(data.title ?? 'Alert'),
        message: String(data.message ?? ''),
        ts: Number(data.ts ?? Date.now() / 1000),
      })
    }
  }

  const alerts = ref<AlertItem[]>([])
  const alertRules = ref<AlertRulesPayload | null>(null)
  const alertRulesSaving = ref(false)
  const alertRulesError = ref<string | null>(null)
  const alertTesting = ref(false)
  const alertTestResult = ref<AlertTestResult | null>(null)
  const alertTestError = ref<string | null>(null)

  let audioCtx: AudioContext | null = null

  function playAlertBeep() {
    try {
      const Ctor = window.AudioContext ?? (window as any).webkitAudioContext
      if (!Ctor) return
      audioCtx = audioCtx ?? new Ctor()
      const ctx = audioCtx
      if (ctx.state === 'suspended') void ctx.resume()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = 880
      gain.gain.setValueAtTime(0.08, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.4)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start()
      osc.stop(ctx.currentTime + 0.4)
    } catch { /* best-effort */ }
  }

  function pushAlert(a: AlertItem) {
    const uid = `${a.id}-${Date.now()}`
    alerts.value.push({ ...a, uid })
    if (alerts.value.length > 5) alerts.value.shift()
    if (alertRules.value?.channels.sound) playAlertBeep()
    window.setTimeout(() => dismissAlert(uid), 12000)
  }

  function dismissAlert(uid: string) {
    const i = alerts.value.findIndex(x => x.uid === uid)
    if (i >= 0) alerts.value.splice(i, 1)
  }

  async function loadAlertRules() {
    try {
      const resp = await fetch('/api/alerts/rules')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      alertRules.value = {
        rules: Array.isArray(data?.rules) ? data.rules : [],
        channels: normalizeAlertChannels(data?.channels),
      }
      alertRulesError.value = null
    } catch (err: any) {
      alertRulesError.value = String(err?.message ?? err)
    }
  }

  async function sendAlertTest(): Promise<boolean> {
    alertTesting.value = true
    alertTestError.value = null
    alertTestResult.value = null
    try {
      const resp = await fetch('/api/alerts/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: 'Test alert',
          message: 'Test notification from Windy Smart Dashboard',
        }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      alertTestResult.value = {
        ok: data?.ok ?? true,
        channels: (data?.channels ?? {}) as Record<string, boolean>,
      }
      return true
    } catch (err: any) {
      alertTestError.value = String(err?.message ?? err)
      return false
    } finally {
      alertTesting.value = false
    }
  }

  async function saveAlertRules(payload: AlertRulesPayload): Promise<boolean> {
    alertRulesSaving.value = true
    alertRulesError.value = null
    try {
      const resp = await fetch('/api/alerts/rules', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!resp.ok) {
        const detail = await resp.json().catch(() => null)
        throw new Error(String(detail?.detail ?? `HTTP ${resp.status}`))
      }
      const data = await resp.json()
      alertRules.value = {
        rules: Array.isArray(data?.rules) ? data.rules : [],
        channels: normalizeAlertChannels(data?.channels),
      }
      return true
    } catch (err: any) {
      alertRulesError.value = String(err?.message ?? err)
      return false
    } finally {
      alertRulesSaving.value = false
    }
  }

  async function runSpeedtest() {
    speedtestRunning.value = true
    speedtest.value = null
    try {
      const resp = await fetch('/api/speedtest', { method: 'POST' })
      const data = await resp.json()
      speedtest.value = data
    } catch (err: any) {
      speedtest.value = { ok: false, error: String(err) }
    } finally {
      speedtestRunning.value = false
    }
  }

  const cpuOverall = computed(() => cpu.value?.overall ?? 0)
  const ramPercent = computed(() => ram.value?.percent ?? 0)
  const sensorStatus = computed(() => system.value?.sensors ?? null)

  return {
    cpu, ram, disk, network, system, gpu, processes, ping,
    cpuHistory, ramHistory, netSendHistory, netRecvHistory,
    speedtest, speedtestRunning,
    alerts, alertRules, alertRulesSaving, alertRulesError,
    alertTesting, alertTestResult, alertTestError,
    cpuOverall, ramPercent, sensorStatus,
    connect, runSpeedtest, dismissAlert, loadAlertRules, saveAlertRules, sendAlertTest,
  }
})
