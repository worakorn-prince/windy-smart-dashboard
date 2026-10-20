const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'] as const

export function formatBytes(bytes: unknown, digits = 1): string {
  const value = Number(bytes)
  if (!Number.isFinite(value)) return '—'
  let scaled = Math.abs(value)
  let unit = 0
  while (scaled >= 1024 && unit < BYTE_UNITS.length - 1) {
    scaled /= 1024
    unit += 1
  }
  const rounded = unit === 0 ? String(Math.round(scaled)) : scaled.toFixed(digits)
  return `${value < 0 ? '-' : ''}${rounded} ${BYTE_UNITS[unit]}`
}

export function formatDuration(ms: unknown, digits = 1): string {
  const value = Number(ms)
  if (!Number.isFinite(value) || value < 0) return '—'
  if (value < 1000) return `${Math.round(value)} ms`
  const seconds = value / 1000
  if (seconds < 60) return `${seconds.toFixed(digits)} s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} m ${Math.round(seconds - minutes * 60)} s`
  return `${Math.floor(minutes / 60)} h ${minutes % 60} m`
}

export function formatPercent(part: unknown, total: unknown, digits = 0): string {
  const p = Number(part)
  const t = Number(total)
  if (!Number.isFinite(p) || !Number.isFinite(t) || t <= 0) return ''
  return `${((p / t) * 100).toFixed(digits)}%`
}
