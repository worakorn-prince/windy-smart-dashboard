import { test, expect, type Page, type Route } from '@playwright/test'

const NOW = 1_700_000_000_000 / 1000

interface Envelope {
  generated_at: number
  data_window: { start: number; end: number }
  source: string
  status: string
  errors: string[]
  coverage: number
}

function envelope(): Envelope {
  return {
    generated_at: NOW,
    data_window: { start: NOW - 3600, end: NOW },
    source: 'e2e-mock',
    status: 'ok',
    errors: [],
    coverage: 1,
  }
}

function makeTarget(targetId: string, address: string, overrides: Record<string, unknown> = {}) {
  return {
    target_id: targetId,
    address,
    probe_type: 'icmp',
    latency_ms: { min: 5, median: 12.5, p95: 30, max: 80, count: 100, timeouts: 1 },
    jitter_ms: 2.5,
    loss_pct: 0.5,
    status: 'ok',
    last_probe_at: NOW,
    ...overrides,
  }
}

function makeInterface(id: string, name: string) {
  return {
    id,
    name,
    description: `E2E ${name}`,
    mac: '00:11:22:33:44:55',
    type: 'ethernet',
    speed_mbps: 1000,
    status: 'up',
    connection_name: name,
    manufacturer: 'Mock',
    ipv4: ['192.168.1.10'],
    ipv6: [],
    gateway: ['192.168.1.1'],
    dns: ['1.1.1.1'],
    current_rates: { send_bps: 1024, recv_bps: 4096 },
    errors: { in: 0, out: 0, discards_in: 0, discards_out: 0 },
  }
}

const qualityTargets = [
  makeTarget('primary', '1.1.1.1'),
  makeTarget('secondary', '8.8.8.8'),
  makeTarget('gateway', '192.168.1.1'),
]

const overviewFixture = {
  connection_status: 'connected',
  internet_quality: {
    primary: qualityTargets[0],
    secondary: qualityTargets[1],
    gateway: qualityTargets[2],
  },
  current_throughput: { send_bps: 2048, recv_bps: 8192, interface_id: 'eth0' },
  active_interface: makeInterface('eth0', 'Ethernet'),
  recent_incidents: [
    { id: 'inc-1', started_at: NOW - 600, category: 'latency', severity: 'warn', title: 'E2E incident' },
  ],
  dns_health: { configured: ['1.1.1.1', '8.8.8.8'], primary_status: 'ok', secondary_status: 'ok' },
  ...envelope(),
}

const qualityFixture = { targets: qualityTargets, ...envelope() }

const interfacesFixture = { interfaces: [makeInterface('eth0', 'Ethernet')], ...envelope() }

const qualityStatusFixture = {
  range: '1h',
  overall: {
    status: 'good',
    badge: 'ดี',
    confidence: 0.9,
    evidence: [],
    degraded_targets: [],
    analyzed_at: NOW,
  },
  targets: {
    primary: {
      target_id: 'primary',
      status: 'good',
      sample_count: 100,
      degraded: false,
      degradation_reason: null,
      degradation_confidence: 0,
    },
  },
  generated_at: NOW,
  data_window: { start: NOW - 3600, end: NOW },
  source: 'e2e-mock',
  status: 'ok',
  errors: [],
  coverage: 1,
}

function bucketedPoints(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    ts: NOW - (n - i) * 60,
    latency: { min: 5, median: 12 + (i % 5), p95: 30, max: 80 },
    count: 10,
  }))
}

const qualityHistoryFixture = { target_id: 'primary', range: '1h', step: 60, points: bucketedPoints(20), ...envelope() }

const tcpStatsFixture = {
  samples: [
    {
      ts: NOW,
      active_opens: 10,
      passive_opens: 4,
      failed_attempts: 0,
      established_resets: 0,
      current_established: 8,
      segments_sent: 500,
      segments_received: 480,
      segments_retransmitted: 2,
      source: 'e2e-mock',
    },
  ],
  ...envelope(),
}

const interfaceHistoryFixture = {
  interface_id: 'eth0',
  range: '1h',
  step: 60,
  points: [
    {
      ts: NOW,
      bytes_sent: 1000,
      bytes_recv: 4000,
      send_bps: 2048,
      recv_bps: 8192,
      packets_sent: 20,
      packets_recv: 40,
      errors_in: 0,
      errors_out: 0,
    },
  ],
  ...envelope(),
}

const dnsFixture = {
  configured_resolvers: ['1.1.1.1', '8.8.8.8'],
  resolver_health: [
    { resolver: '1.1.1.1', status: 'ok', avg_latency_ms: 11.2, success_rate: 1, recent_probes: 50, last_probe_at: NOW },
    { resolver: '8.8.8.8', status: 'degraded', avg_latency_ms: 45, success_rate: 0.8, recent_probes: 50, last_probe_at: NOW },
  ],
  ...envelope(),
}

const dnsHistoryFixture = { range: '1h', step: 60, points: bucketedPoints(10), ...envelope() }

const dnsCompareFixture = {
  hostname: 'example.test',
  record_type: 'A',
  comparison: [
    { resolver: '1.1.1.1', probe_method: 'udp', duration_ms: 12, status: 'success', answer_count: 2, error_code: null },
    { resolver: '8.8.8.8', probe_method: 'udp', duration_ms: 40, status: 'success', answer_count: 2, error_code: null },
  ],
  ...envelope(),
}

const routesFixture = {
  routes: [
    { destination: '0.0.0.0', prefix_length: 0, next_hop: '192.168.1.1', interface_index: 1, metric: 0, protocol: 3, age: 3600, origin: 3, is_default: true },
    { destination: '192.168.1.0', prefix_length: 24, next_hop: null, interface_index: 1, metric: 10, protocol: 2, age: 7200, origin: 2, is_default: false },
  ],
  default_gateway: '192.168.1.1',
  gateway_interface_index: 1,
  snapshot_ts: NOW,
  ...envelope(),
}

const routesHistoryFixture = {
  range: '1h',
  changes: [
    { timestamp: NOW - 600, change_type: 'add', details: { destination: '10.0.0.0/8' }, severity: 'info' },
  ],
  ...envelope(),
}

function tracerouteFixture(target: string) {
  return {
    session_id: 'tr-e2e-1',
    target,
    max_hops: 10,
    protocol: 'icmp',
    hops: [
      { hop: 1, address: '192.168.1.1', rtt_ms: 1.2, status: 'ok' },
      { hop: 2, address: '10.0.0.1', rtt_ms: 8.5, status: 'ok' },
      { hop: 3, address: '1.2.3.4', rtt_ms: null, status: 'timeout' },
    ],
    ...envelope(),
  }
}

const incidentsFixture = {
  incidents: [
    {
      id: 'inc-1',
      started_at: NOW - 600,
      ended_at: null,
      category: 'latency',
      severity: 'warn',
      status: 'active',
      title: 'E2E incident',
      summary: 'mock',
      confidence: 0.8,
      analyzer_version: '1',
    },
  ],
  status: 'ok',
  errors: [],
}

function sessionFixture(id: string, status: string) {
  return {
    id,
    started_at: NOW,
    status,
    profile: 'quick',
    config: {},
    summary: {
      ping_success_rate: 0.9,
      packet_loss_pct: 0.5,
      dns_success_rate: 1,
      avg_rtt_ms: 12.5,
    },
  }
}

const sessionResultsFixture = {
  session_id: 'ses-e2e-1',
  status: 'completed',
  results: [
    { sequence: 1, result_type: 'ping', ts: new Date(NOW * 1000).toISOString(), payload: { rtt_ms: 10, status: 'ok' } },
    { sequence: 2, result_type: 'dns', ts: new Date(NOW * 1000).toISOString(), payload: { status: 'ok', answer_count: 2 } },
  ],
}

function sessionIdFromPath(path: string): string {
  const idx = path.indexOf('/sessions/')
  return idx >= 0 ? path.slice(idx + '/sessions/'.length).split('/')[0] : 'ses-e2e-1'
}

async function installInternetMocks(page: Page): Promise<void> {
  await page.route('**/api/internet/**', async (route: Route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const json = (body: unknown) => route.fulfill({ status: 200, json: body as object })

    if (path.endsWith('/overview')) return json(overviewFixture)
    if (path.endsWith('/quality/status')) return json(qualityStatusFixture)
    if (path.endsWith('/quality/history')) return json(qualityHistoryFixture)
    if (path.endsWith('/quality')) return json(qualityFixture)
    if (path.endsWith('/tcp/stats')) return json(tcpStatsFixture)
    if (path.includes('/interfaces/') && path.endsWith('/history')) return json(interfaceHistoryFixture)
    if (path.endsWith('/interfaces')) return json(interfacesFixture)
    if (path.endsWith('/dns/history')) return json(dnsHistoryFixture)
    if (path.endsWith('/dns/compare')) {
      return json({
        ...dnsCompareFixture,
        hostname: url.searchParams.get('hostname') ?? dnsCompareFixture.hostname,
        record_type: url.searchParams.get('record_type') ?? dnsCompareFixture.record_type,
      })
    }
    if (path.endsWith('/dns')) return json(dnsFixture)
    if (path.endsWith('/routes/history')) return json(routesHistoryFixture)
    if (path.endsWith('/routes/traceroute')) {
      return json(tracerouteFixture(url.searchParams.get('target') ?? '8.8.8.8'))
    }
    if (path.endsWith('/routes')) return json(routesFixture)
    if (path.endsWith('/incidents')) return json(incidentsFixture)
    if (path.endsWith('/sessions') && route.request().method() === 'POST') {
      return json(sessionFixture('ses-e2e-1', 'running'))
    }
    if (path.includes('/sessions/') && path.endsWith('/cancel')) {
      return json({ id: sessionIdFromPath(path), status: 'cancelled' })
    }
    if (path.includes('/sessions/') && path.endsWith('/results')) {
      return json(sessionResultsFixture)
    }
    if (path.includes('/sessions/') && path.endsWith('/export')) {
      return route.fulfill({ status: 200, body: '{"e2e":true}', contentType: 'application/json' })
    }
    if (path.includes('/sessions/')) {
      return json(sessionFixture(sessionIdFromPath(path), 'running'))
    }
    return json({ ...envelope() })
  })
}

async function gotoInternetPage(page: Page, path: string): Promise<void> {
  await page.goto(path)
  await page.waitForLoadState('domcontentloaded')
}

test.describe('Internet Insights E2E', () => {
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000)
    page.on('pageerror', () => {})
    await installInternetMocks(page)
  })

  test('insights page loads overview cards without error state', async ({ page }) => {
    await gotoInternetPage(page, '/internet-insights')

    await expect(page.getByTestId('internet-insights-page')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('stat-connection-status')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('internet-overview-grid')).toBeVisible()
    await expect(page.getByTestId('stat-active-interface')).toBeVisible()
    await expect(page.getByTestId('stat-upload')).toBeVisible()
    await expect(page.getByTestId('stat-download')).toBeVisible()
    await expect(page.getByTestId('stat-incidents')).toBeVisible()
    await expect(page.getByTestId('error-state')).toHaveCount(0)
  })

  test('quality targets render from fixture with charts grid', async ({ page }) => {
    await gotoInternetPage(page, '/internet-insights')

    await expect(page.getByTestId('quality-gateway')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('quality-primary')).toBeVisible()
    await expect(page.getByTestId('quality-secondary')).toBeVisible()
    await expect(page.getByTestId('quality-charts-grid')).toBeVisible()
    await expect(page.getByTestId('stat-latency-median').first()).toContainText('12.5')
    await expect(page.getByTestId('error-state')).toHaveCount(0)
  })

  test('quality range selector switches active range', async ({ page }) => {
    await gotoInternetPage(page, '/internet-insights')

    const selector = page.getByTestId('quality-range-selector')
    await expect(selector).toBeVisible({ timeout: 60_000 })

    // Range buttons carry a class, not a testid; scope to the selector.
    const buttons = selector.locator('button.range-btn')
    const count = await buttons.count()
    expect(count).toBeGreaterThan(1)
    await buttons.nth(count - 1).click()
    await expect(page.getByTestId('quality-gateway')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('error-state')).toHaveCount(0)
  })

  test('dns page shows resolver cards and status counts from fixture', async ({ page }) => {
    await gotoInternetPage(page, '/internet-dns')

    await expect(page.getByTestId('dns-resolver-cards')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('dns-count-ok')).toContainText('1')
    await expect(page.getByTestId('dns-count-degraded')).toContainText('1')
    await expect(page.getByTestId('internet-dns-page')).toBeVisible()
    await expect(page.getByTestId('dns-error-state')).toHaveCount(0)
    await expect(page.getByTestId('dns-empty-resolvers')).toHaveCount(0)
  })

  test('dns compare runs against mocked endpoint and shows modal', async ({ page }) => {
    await gotoInternetPage(page, '/internet-dns')
    await expect(page.getByTestId('dns-resolver-cards')).toBeVisible({ timeout: 60_000 })

    const compareSection = page.getByTestId('dns-compare-section')
    await expect(compareSection).toBeVisible()
    await page.getByTestId('dns-compare-hostname').fill('example.test')
    await page.getByTestId('dns-compare-record-type').selectOption('A')
    await page.getByTestId('dns-compare-run').click()

    // The testid exists on both the overlay and the inner content; take the
    // outermost so table/row lookups stay scoped inside the modal.
    const modal = page.getByTestId('dns-comparison-modal').first()
    await expect(modal).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('dns-comparison-table')).toBeVisible()

    const rows = modal.locator('tbody tr')
    await expect(rows).toHaveCount(2)
    await expect(rows.first()).toContainText('1.1.1.1')
    await expect(rows.first()).toContainText('12')
  })

  test('traceroute runs against mocked endpoint and renders hops', async ({ page }) => {
    await gotoInternetPage(page, '/internet-routing')

    await expect(page.getByTestId('internet-routing-page')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('routes-section')).toBeVisible()
    await expect(page.getByTestId('route-table')).toBeVisible()
    await expect(page.getByTestId('routing-error-state')).toHaveCount(0)

    // Both the form button and TracerouteView's internal button share the same
    // testid; scope to the form to keep Playwright strict mode happy.
    const runBtn = page.getByTestId('traceroute-form').getByTestId('traceroute-run-btn')
    await page.getByTestId('traceroute-target-input').fill('1.2.3.4')
    await runBtn.click()

    await expect(page.getByTestId('traceroute-view')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('traceroute-table')).toBeVisible()
    for (const hop of ['traceroute-hop-1', 'traceroute-hop-2', 'traceroute-hop-3']) {
      await expect(page.getByTestId(hop)).toBeVisible()
    }
    await expect(page.getByTestId('traceroute-hop-1')).toContainText('192.168.1.1')
    await expect(page.getByTestId('traceroute-hop-2')).toContainText('10.0.0.1')
    await expect(page.getByTestId('traceroute-hop-3')).toContainText('1.2.3.4')
    await expect(page.getByTestId('routing-error-state')).toHaveCount(0)
  })

  test('session starts against mocked endpoint and badge shows running', async ({ page }) => {
    await gotoInternetPage(page, '/internet-diagnostics')

    await expect(page.getByTestId('internet-diagnostics-page')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('session-section')).toBeVisible()

    await page.getByTestId('session-start-btn').click()
    await expect(page.getByTestId('session-status-badge')).toHaveText('running', { timeout: 60_000 })
    await expect(page.getByTestId('session-results')).toBeVisible()
    await expect(page.getByTestId('session-results-table')).toBeVisible()
    await expect(page.getByTestId('session-result-row').first()).toContainText('ping')
    await expect(page.getByTestId('session-error-state')).toHaveCount(0)
  })

  test('cancel stops a running session and badge flips to cancelled', async ({ page }) => {
    await gotoInternetPage(page, '/internet-diagnostics')

    await expect(page.getByTestId('session-section')).toBeVisible({ timeout: 60_000 })
    await page.getByTestId('session-start-btn').click()
    await expect(page.getByTestId('session-status-badge')).toHaveText('running', { timeout: 60_000 })

    await page.getByTestId('session-cancel-btn').click()
    await expect(page.getByTestId('session-status-badge')).toHaveText('cancelled', { timeout: 60_000 })
    await expect(page.getByTestId('session-error-state')).toHaveCount(0)
  })

  test('session report view and json export trigger a download', async ({ page }) => {
    await gotoInternetPage(page, '/internet-diagnostics')

    await expect(page.getByTestId('session-section')).toBeVisible({ timeout: 60_000 })
    await page.getByTestId('session-start-btn').click()
    await expect(page.getByTestId('session-results')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('session-result-row').nth(1)).toContainText('dns')

    const exportBtn = page.getByTestId('session-export-json')
    await expect(exportBtn).toBeVisible()
    const downloadPromise = page.waitForEvent('download', { timeout: 30_000 })
    await exportBtn.click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('session-ses-e2e-1.json')
    await expect(page.getByTestId('session-error-state')).toHaveCount(0)
  })

  test('existing dashboard, security, maintenance and insights pages remain functional', async ({ page }) => {
    await gotoInternetPage(page, '/')
    await expect(page.getByTestId('dashboard-head')).toBeVisible({ timeout: 60_000 })

    await gotoInternetPage(page, '/security')
    await expect(page.getByRole('heading', { name: /Live Security Events/ })).toBeVisible({ timeout: 60_000 })

    await gotoInternetPage(page, '/maintenance')
    await expect(page.getByRole('heading', { level: 1, name: /บำรุงรักษาระบบ/ })).toBeVisible({ timeout: 60_000 })

    await gotoInternetPage(page, '/insights')
    await expect(page.getByTestId('insights-head')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('insights-range-tabs')).toBeVisible({ timeout: 60_000 })
  })
})
