import { describe, expect, it } from 'vitest'
import {
  epochSecToDate,
  formatBps,
  formatMemMb,
  formatNaiveStamp,
  formatRatePct,
  formatSignedGb,
  isoTextToDate,
} from '@/utils/insights'

describe('insights utils — epoch (effective_window) vs ISO TEXT parsing', () => {
  it('parses epoch REAL seconds from effective_window', () => {
    const d = epochSecToDate(1_763_500_000)
    expect(d).not.toBeNull()
    expect(d!.getTime()).toBe(1_763_500_000 * 1000)
  })

  it('parses disk first_ts/last_ts ISO TEXT with microseconds + Z as UTC', () => {
    const d = isoTextToDate('2026-10-20T09:00:00.123456Z')
    expect(d!.getTime()).toBe(Date.UTC(2026, 9, 20, 9, 0, 0, 123))
  })

  it('parses ISO TEXT without fractional seconds', () => {
    const d = isoTextToDate('2026-11-20T17:55:00Z')
    expect(d!.getTime()).toBe(Date.UTC(2026, 10, 20, 17, 55, 0))
  })

  it('treats naive local stamps (security_events/generated_at) as local wall clock, not UTC', () => {
    const naive = '2026-01-01T10:30:00'
    const d = isoTextToDate(naive)
    const local = new Date(2026, 0, 1, 10, 30, 0)
    expect(d!.getTime()).toBe(local.getTime())
    expect(d!.getTime()).not.toBe(Date.UTC(2026, 0, 1, 10, 30, 0))
  })

  it('renders naive stamps as-is (never shifted to UTC)', () => {
    expect(formatNaiveStamp('2026-11-20T18:00:00')).toBe('2026-11-20 18:00:00')
    expect(formatNaiveStamp('2026-11-20T18:00:00.123456')).toBe('2026-11-20 18:00:00')
    expect(formatNaiveStamp('2026-11-20T18:00:00Z')).toBe('2026-11-20 18:00:00')
    expect(formatNaiveStamp('')).toBe('—')
    expect(formatNaiveStamp(42)).toBe('—')
  })

  it('returns null for invalid values', () => {
    expect(epochSecToDate(null)).toBeNull()
    expect(epochSecToDate(0)).toBeNull()
    expect(isoTextToDate('not a date')).toBeNull()
    expect(isoTextToDate('')).toBeNull()
  })
})

describe('insights utils — value formatters', () => {
  it('formats GB values with fallback dash', () => {
    expect(formatSignedGb(2.5)).toBe('+2.50 GB')
    expect(formatSignedGb(-1.25)).toBe('-1.25 GB')
    expect(formatSignedGb(null)).toBe('—')
  })

  it('formats memory MB to GB when large', () => {
    expect(formatMemMb(2048)).toBe('2.00 GB')
    expect(formatMemMb(512)).toBe('512 MB')
    expect(formatMemMb(undefined)).toBe('—')
  })

  it('formats bps to MB/s', () => {
    expect(formatBps(2 * 1024 * 1024)).toBe('2.00 MB/s')
    expect(formatBps(null)).toBe('—')
  })

  it('treats null success rate as null (never 0%)', () => {
    expect(formatRatePct(null)).toBeNull()
    expect(formatRatePct(0.9)).toBe('90.0%')
    expect(formatRatePct(0)).toBe('0.0%')
    expect(formatRatePct(undefined)).toBeNull()
  })
})
