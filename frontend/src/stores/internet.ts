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

export interface BucketedLatencyPoint {
  ts: number
  latency: {
    min: number
    median: number
    p95: number
    max: number
  }
  count: number
}

export interface QualityHistoryData {
  target_id: string
  range: string
  step: number
  points: (HistoryPoint | BucketedLatencyPoint)[]
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

// Quality Status types
export interface QualityTargetStatus {
  target_id: string
  latency_median_ms: number | null
  jitter_ms: number | null
  loss_pct: number
  last_probe_at: number | null
  sample_count: number
  degraded: boolean
  degradation_reason: string | null
  degradation_confidence: number
}

export interface QualityOverallStatus {
  status: 'good' | 'degraded' | 'poor' | 'unknown'
  badge: string
  confidence: number
  evidence: QualityTargetStatus[]
  degraded_targets: string[]
  analyzed_at: number
}

export interface QualityStatusData {
  range: string
  overall: QualityOverallStatus
  targets: Record<string, QualityTargetStatus>
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

// TCP Stats types
export interface TcpStatsSample {
  ts: number
  active_opens: number
  passive_opens: number
  failed_attempts: number
  established_resets: number
  current_established: number
  segments_sent: number
  segments_received: number
  segments_retransmitted: number
  source: string
}

export interface TcpStatsData {
  range: string
  current: TcpStatsSample | null
  history: TcpStatsSample[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

// DNS types
export interface DnsResolverHealth {
  resolver: string
  status: 'ok' | 'degraded' | 'down' | 'unknown'
  avg_latency_ms: number | null
  success_rate: number
  recent_probes: number
  last_probe_at: number | null
}

export interface DnsData {
  configured_resolvers: string[]
  resolver_health: DnsResolverHealth[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface DnsHistoryPoint {
  ts: number
  resolver: string
  hostname: string
  record_type: string
  duration_ms: number | null
  status: string
  answer_count: number
  error_code: string | null
  probe_method: string
}

export interface DnsBucketedPoint {
  ts: number
  latency: {
    min: number
    median: number
    p95: number
    max: number
  }
  count: number
}

export interface DnsHistoryData {
  range: string
  step: number
  points: (DnsHistoryPoint | DnsBucketedPoint)[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface DnsComparisonResult {
  resolver: string
  probe_method: string
  duration_ms: number | null
  status: string
  answer_count: number
  error_code: string | null
}

export interface DnsCompareData {
  hostname: string
  record_type: string
  comparison: DnsComparisonResult[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

// Route types
export interface RouteEntry {
  destination: string
  prefix_length: number
  next_hop: string | null
  interface_index: number
  metric: number
  protocol: number
  age: number
  origin: number
  is_default: boolean
}

export interface RoutesData {
  routes: RouteEntry[]
  default_gateway: string | null
  gateway_interface_index: number | null
  snapshot_ts: number | null
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface TracerouteHop {
  hop: number
  address: string | null
  rtt_ms: number | null
  status: string
}

export interface TracerouteData {
  session_id: string
  target: string
  max_hops: number
  protocol: string
  hops: TracerouteHop[]
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

export interface RouteChange {
  timestamp: number
  change_type: string
  details: Record<string, unknown>
  severity: string
}

export interface RoutesHistoryData {
  range: string
  changes: RouteChange[]
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
  const qualityStatus = ref<QualityStatusData | null>(null)
  const tcpStats = ref<TcpStatsData | null>(null)
  const dns = ref<DnsData | null>(null)
  const dnsHistory = ref<DnsHistoryData | null>(null)
  const dnsCompare = ref<DnsCompareData | null>(null)
  const routes = ref<RoutesData | null>(null)
  const traceroute = ref<TracerouteData | null>(null)
  const routesHistory = ref<RoutesHistoryData | null>(null)

  const loading = ref(false)
  const error = ref<string | null>(null)

  const isConnected = computed(() => overview.value?.connection_status === 'connected')
  const isDegraded = computed(() => overview.value?.connection_status === 'degraded')
  const primaryLatency = computed(() => {
    let target = quality.value?.targets?.find(t => t.target_id === 'primary')
    if (target?.latency_ms?.median != null) return target.latency_ms.median
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

  const qualityBadge = computed(() => qualityStatus.value?.overall.badge ?? '—')
  const qualityOverallStatus = computed(() => qualityStatus.value?.overall.status ?? 'unknown')

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

  async function loadQualityHistory(
    range: '5m' | '1h' | '6h' | '24h' | '7d' | '30d' = '1h',
    targetId = 'primary',
    step = 60
  ) {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/quality/history?range=${range}&target_id=${targetId}&step=${step}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      qualityHistory.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadQualityStatus(range: '5m' | '1h' | '6h' | '24h' | '7d' | '30d' = '1h') {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/quality/status?range=${range}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      qualityStatus.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadTcpStats(range: '5m' | '1h' | '6h' | '24h' | '7d' | '30d' = '1h') {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/tcp/stats?range=${range}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      tcpStats.value = data
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

  // DNS actions
  async function loadDns() {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch('/api/internet/dns')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      dns.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadDnsHistory(
    range: '5m' | '1h' | '6h' | '24h' | '7d' | '30d' = '1h',
    step = 60
  ) {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/dns/history?range=${range}&step=${step}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      dnsHistory.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadDnsCompare(hostname: string, recordType = 'A') {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/dns/compare?hostname=${encodeURIComponent(hostname)}&record_type=${encodeURIComponent(recordType)}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      dnsCompare.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  // Route actions
  async function loadRoutes() {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch('/api/internet/routes')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      routes.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadTraceroute(target: string, maxHops = 30, protocol = 'icmp') {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/routes/traceroute?target=${encodeURIComponent(target)}&max_hops=${maxHops}&protocol=${encodeURIComponent(protocol)}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      traceroute.value = data
    } catch (err: any) {
      error.value = String(err?.message ?? err)
    } finally {
      loading.value = false
    }
  }

  async function loadRoutesHistory(range: '5m' | '1h' | '6h' | '24h' | '7d' | '30d' = '1h') {
    loading.value = true
    error.value = null
    try {
      const resp = await fetch(`/api/internet/routes/history?range=${range}`)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      routesHistory.value = data
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
    qualityStatus,
    tcpStats,
    dns,
    dnsHistory,
    dnsCompare,
    routes,
    traceroute,
    routesHistory,
    loading,
    error,
    isConnected,
    isDegraded,
    primaryLatency,
    primaryLoss,
    gatewayLatency,
    qualityBadge,
    qualityOverallStatus,
    loadOverview,
    loadQuality,
    loadInterfaces,
    loadQualityHistory,
    loadQualityStatus,
    loadTcpStats,
    loadInterfaceHistory,
    loadDns,
    loadDnsHistory,
    loadDnsCompare,
    loadRoutes,
    loadTraceroute,
    loadRoutesHistory,
    loadAll,
  }
})