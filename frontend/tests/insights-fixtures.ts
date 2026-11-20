export const INSIGHTS_FIXTURE = {
  range: '24h',
  generated_at: '2026-11-20T18:00:00',
  effective_window: { start: 1_763_500_000, end: 1_763_536_000, n: 1200 },
  trends: {
    range: '24h',
    bucket_sec: 60,
    count: 2,
    points: [
      {
        ts: 1_763_500_000,
        cpu_pct: 10.5, ram_pct: 40.2, swap_pct: 1.1,
        cpu_temp: 45.0, gpu_temp: 50.0, disk_temp_max: 40.0,
        cpu_power_w: 12.0, gpu_power_w: 30.0,
        net_sent_bps: 1_000, net_recv_bps: 2_000,
        disk_read_bps: 3_000, disk_write_bps: 4_000,
      },
      {
        ts: 1_763_500_060,
        cpu_pct: 20.5, ram_pct: 50.2, swap_pct: 2.1,
        cpu_temp: null, gpu_temp: null, disk_temp_max: null,
        cpu_power_w: null, gpu_power_w: null,
        net_sent_bps: 1_500, net_recv_bps: 2_500,
        disk_read_bps: 3_500, disk_write_bps: 4_500,
      },
    ],
  },
  disk: [
    {
      mount: 'C:\\',
      used_gb: 120.5,
      total_gb: 476.9,
      first_used_gb: 118.0,
      avg_used_gb: 119.5,
      peak_used_gb: 121.0,
      delta_gb: 2.5,
      n: 100,
      first_ts: '2026-10-20T09:00:00.123456Z',
      last_ts: '2026-11-20T17:55:00.654321Z',
    },
  ],
  top_processes: [
    { name: 'chrome.exe', avg_cpu_pct: 12.34, peak_mem_mb: 2048, n: 500 },
  ],
  maintenance: {
    total: 10,
    ok: 9,
    failed: 1,
    success_rate: 0.9,
    by_action: [
      { action: 'cleanup', count: 10, ok: 9, failed: 1, success_rate: 0.9 },
    ],
  },
  security: {
    total: 42,
    by_kind: [{ kind: 'port_open', count: 30 }],
    top_sources: [{ source_ip: '192.168.1.10', count: 12 }],
  },
  baseline: {
    cpu_pct: { mode: 'flat', hours: {}, n: 1200, mean: 15, std: 5, lo: 0, hi: 30 },
    net_recv_bps: { mode: 'hourly', hours: { '9': { n: 20, mean: 1, std: 0.5, lo: 0, hi: 2.5 } }, n: 1200, mean: 1, std: 0.5, lo: 0, hi: 2.5 },
  },
  anomalies: [
    { metric: 'cpu_pct', ts: 1_763_530_000, value: 95, expected: 15, z: 4.2, direction: 'high', run_len: 3 },
  ],
}

export const EMPTY_INSIGHTS_FIXTURE = {
  range: '30d',
  generated_at: '2026-11-20T18:00:00',
  effective_window: null,
  trends: { range: '30d', bucket_sec: 900, count: 0, points: [] },
  disk: [],
  top_processes: [],
  maintenance: { total: 0, ok: 0, failed: 0, success_rate: null, by_action: [] },
  security: { total: 0, by_kind: [], top_sources: [] },
  baseline: {},
  anomalies: [],
}
