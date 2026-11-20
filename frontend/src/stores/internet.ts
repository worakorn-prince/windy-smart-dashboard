import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface QualityTarget {
  target_id: string
  address: string
  probe_type: string
  latency_ms: {
    min: number | null
    median: number | null
    p95: number | null
    max: number | null
    count: number
    timeouts: number
  }
  jitter_ms: number | null
  loss_pct: number
  status: string
  last_probe_at: number
}

export interface InterfaceInfo {
  id: string
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
  current_rates: {
    send_bps: number
    recv_bps: number
  }
  errors: {
    in: number
    out: number
    discards_in: number
    discards_out: number
  }
}

export interface OverviewData {
  connection_status: 'connected' | 'degraded' | 'disconnected'
  internet_quality: {
    primary: QualityTarget
    secondary: QualityTarget
    gateway: QualityTarget
  }
  current_throughput: {
    send_bps: number
    recv_bps: number
    interface_id: string | null
  }
  active_interface: InterfaceInfo | null
  recent_incidents: Array<{
    id: string
    started_at: number
    category: string
    severity: string
    title: string
  }>
  dns_health: {
    configured: string[]
    primary_status: string
    secondary_status: string
  }
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface QualityData {
  targets: QualityTarget[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface InterfacesData {
  interfaces: InterfaceInfo[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface HistoryPoint {
  ts: number
  target_id?: string
  probe_type?: string
  rtt_ms: number | null
  status: string
  error_code: string | null
}

export interface QualityHistoryData {
  target_id: string
  range: string
  points: HistoryPoint[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface InterfaceHistoryPoint {
  ts: number
  bytes_sent: number
  bytes_recv: number
  send_bps: number
  recv_bps: number
  packets_sent: number
  packets_recv: number
  errors_in: number
  errors_out: number
  discards_in: number
  discards_out: number
  link_status: string | null
}

export interface InterfaceHistoryData {
  interface_id: string
  range: string
  points: InterfaceHistoryPoint[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export const useInternetStore = defineStore('internet', () => {
  const overview = ref<OverviewData | null>(null)
  const quality = ref<QualityData | null>(null)
  const interfaces = ref<InterfacesData | null>(null)
  const qualityHistory = ref<QualityHistoryData | null>(null)
  const interfaceHistory = ref<InterfaceHistoryData | null>(null)

  const loading = ref(false)
  const error = ref<string | null>(null)

  const isConnected = computed(() => overview.value?.connection_status === 'connected')
  const isDegraded = computed(() => overview.value?.connection_status === 'degraded')
  const primaryLatency = computed(() => {
    // First check quality.value (from /api/internet/quality)
    let target = quality.value?.targets?.find(t => t.target_id === 'primary')
    if (target?.latency_ms?.median != null) return target.latency_ms.median
    // Fallback to overview.internet_quality (from /api/internet/overview)
    target = overview.value?.internet_quality?.primary
    return target?.latency_ms?.median ?? null
  })
  const primaryLoss = computed(() => {
    let target = quality.value?.targets?.find(t => t.target_id === 'primary')
    if (target?.loss_pct != null) return target.loss_pct
    target = overview.value?.internet_quality?.primary
    return target?.loss_pct ?? 0
  })
  const gatewayLatency = computed(() => {
    let target = quality.value?.targets?.find(t => t.target_id === 'gateway')
    if (target?.latency_ms?.median != null) return target.latency_ms.median
    target = overview.value?.internet_quality?.gateway
    return target?.latency_ms?.median ?? null
  })

  async function loadOverview() {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch('/api/internet/overview')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      overview.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadQuality() {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch('/api/internet/quality')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      quality.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadInterfaces() {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch('/api/internet/interfaces')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      interfaces.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadQualityHistory(range: '5m' | '1h' | '6h' | '24h' | '7d' | '30d' = '1h', targetId = 'primary') {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/quality/history?range=${range}&target_id=${targetId}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      qualityHistory.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadInterfaceHistory(interfaceId: string, range: '5m' | '1h' | '6h' | '24h' | '7d' | '30d' = '1h') {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/interfaces/${interfaceId}/history?range=${range}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      interfaceHistory.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadAll() {
    await Promise.all([loadOverview(), loadQuality(), loadInterfaces()])
  }

  return {
    overview,
    quality,
    interfaces,
    qualityHistory,
    interfaceHistory,
    loading,
    error,
    isConnected,
    isDegraded,
    primaryLatency,
    primaryLoss,
    gatewayLatency,
    loadOverview,
    loadQuality,
    loadInterfaces,
    loadQualityHistory,
    loadInterfaceHistory,
    loadAll,
  }
})