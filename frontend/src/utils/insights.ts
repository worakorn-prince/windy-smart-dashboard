const BPS_PER_MB = 1024 * 1024

export function formatGb(value: unknown, digits = 1): string {
  if (value == null) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(digits)} GB`
}

export function formatSignedGb(value: unknown): string {
  if (value == null) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)} GB`
}

export function formatMemMb(value: unknown): string {
  if (value == null) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  if (Math.abs(n) >= 1024) return `${(n / 1024).toFixed(2)} GB`
  return `${n.toFixed(0)} MB`
}

export function formatBps(value: unknown): string {
  if (value == null) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return `${(n / BPS_PER_MB).toFixed(2)} MB/s`
}

export function formatRatePct(rate: unknown, digits = 1): string | null {
  if (rate == null) return null
  const n = Number(rate)
  if (!Number.isFinite(n)) return null
  return `${(n * 100).toFixed(digits)}%`
}

export function formatNum(value: unknown, digits = 0): string {
  if (value == null) return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(digits)
}

export function epochSecToDate(value: unknown): Date | null {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return null
  return new Date(n * 1000)
}

const ISO_TEXT_RE = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?(?:\.(\d{1,9}))?(Z|[+-]\d{2}:?\d{2})?$/

export function isoTextToDate(value: unknown): Date | null {
  if (typeof value !== 'string') return null
  const raw = value.trim()
  if (!raw) return null
  const m = ISO_TEXT_RE.exec(raw)
  if (!m) {
    const fallback = new Date(raw)
    return Number.isNaN(fallback.getTime()) ? null : fallback
  }
  const [, date, hm, sec, frac, tz] = m
  const ms = frac ? Number(frac.slice(0, 3).padEnd(3, '0')) : 0
  const normal = `${date}T${hm}:${sec ?? '00'}.${String(ms).padStart(3, '0')}`
  const stamp = tz === undefined ? normal : `${normal}${tz === 'Z' ? 'Z' : tz}`
  const parsed = new Date(stamp)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

export function formatDateTime(d: Date | null): string {
  if (!d) return '—'
  return d.toLocaleString('th-TH', { dateStyle: 'short', timeStyle: 'medium' })
}

export function formatEpochSec(value: unknown): string {
  return formatDateTime(epochSecToDate(value))
}

export function formatIsoText(value: unknown): string {
  return formatDateTime(isoTextToDate(value))
}

export function formatNaiveStamp(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return '—'
  const s = value.trim().replace('T', ' ')
  const noFrac = s.replace(/(\.\d+)/, '')
  return noFrac.endsWith('Z') ? noFrac.slice(0, -1) : noFrac
}

export function formatWindowSpan(startSec: number, endSec: number): string {
  const spanSec = Math.max(0, endSec - startSec)
  const hours = spanSec / 3600
  if (hours >= 48) return `${(hours / 24).toFixed(1)} วัน`
  if (hours >= 1) return `${hours.toFixed(1)} ชม.`
  return `${Math.max(1, Math.round(spanSec / 60))} นาที`
}
