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
  fan_rpm?: number | null
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
  fan_speed_percent?: number | null
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
      if (data.cpu) cpu.value = data.cpu
      if (data.ram) ram.value = data.ram
      if (data.disk) disk.value = data.disk
      if (data.network) network.value = data.network
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

  function pushAlert(a: AlertItem) {
    const uid = `${a.id}-${Date.now()}`
    alerts.value.push({ ...a, uid })
    if (alerts.value.length > 5) alerts.value.shift()
    window.setTimeout(() => dismissAlert(uid), 12000)
  }

  function dismissAlert(uid: string) {
    const i = alerts.value.findIndex(x => x.uid === uid)
    if (i >= 0) alerts.value.splice(i, 1)
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

  return {
    cpu, ram, disk, network, system, gpu, processes, ping,
    cpuHistory, ramHistory, netSendHistory, netRecvHistory,
    speedtest, speedtestRunning,
    alerts,
    cpuOverall, ramPercent,
    connect, runSpeedtest, dismissAlert,
  }
})
