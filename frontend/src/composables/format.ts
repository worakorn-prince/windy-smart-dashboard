export function formatBytes(n: number | null | undefined, decimals = 1): string {
  if (n == null || isNaN(n as any)) return '?'
  const num = Number(n)
  if (num === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(num) / Math.log(k))
  return `${(num / Math.pow(k, i)).toFixed(decimals)} ${sizes[i]}`
}

export function formatRate(bytesPerSec: number): string {
  if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSec / 1024 / 1024).toFixed(2)} MB/s`
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return '-'
  return n.toLocaleString()
}

export function timeAgo(iso: string): string {
  try {
    const dt = new Date(iso).getTime()
    const diff = (Date.now() - dt) / 1000
    if (diff < 60) return `${diff.toFixed(0)}s ago`
    if (diff < 3600) return `${(diff / 60).toFixed(0)}m ago`
    if (diff < 86400) return `${(diff / 3600).toFixed(0)}h ago`
    return `${(diff / 86400).toFixed(0)}d ago`
  } catch {
    return iso
  }
}
