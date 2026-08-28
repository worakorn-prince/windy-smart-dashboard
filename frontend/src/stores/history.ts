import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface HistoryPoint {
  ts: number
  cpu_pct: number | null
  ram_pct: number | null
  swap_pct: number | null
  cpu_temp: number | null
  gpu_temp: number | null
  disk_temp_max: number | null
  cpu_power_w: number | null
  gpu_power_w: number | null
  net_sent_bps: number | null
  net_recv_bps: number | null
  disk_read_bps: number | null
  disk_write_bps: number | null
}

export type HistoryRange = '1h' | '6h' | '24h'

interface HistoryResponse {
  range: string
  bucket_sec: number
  count: number
  points: HistoryPoint[]
}

export const useHistoryStore = defineStore('history', () => {
  const range = ref<HistoryRange>('1h')
  const points = ref<HistoryPoint[]>([])
  const bucketSec = ref(10)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(r?: HistoryRange) {
    if (r) range.value = r
    loading.value = true
    error.value = null
    try {
      const res = await window.fetch(`/api/history?range=${range.value}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as HistoryResponse
      points.value = data.points ?? []
      bucketSec.value = data.bucket_sec ?? 10
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  return { range, points, bucketSec, loading, error, load }
})
