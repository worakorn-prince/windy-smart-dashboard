import { describe, it, expect } from 'vitest'
import { formatBytes, formatDuration, formatPercent } from '@/utils/format'

describe('formatBytes', () => {
  it('formats 0 and small values as bytes', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1023)).toBe('1023 B')
  })

  it('scales to KB/MB/GB', () => {
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(1024 ** 2)).toBe('1.0 MB')
    expect(formatBytes(1024 ** 3)).toBe('1.0 GB')
    expect(formatBytes(1536, 2)).toBe('1.50 KB')
  })

  it('caps at the largest unit (PB)', () => {
    expect(formatBytes(1024 ** 6)).toBe('1024.0 PB')
  })

  it('keeps the sign for negative values', () => {
    expect(formatBytes(-500)).toBe('-500 B')
    expect(formatBytes(-1536)).toBe('-1.5 KB')
  })

  it('returns an em dash for non-finite input', () => {
    expect(formatBytes(NaN)).toBe('—')
    expect(formatBytes(Infinity)).toBe('—')
    expect(formatBytes(undefined)).toBe('—')
    expect(formatBytes('not-a-number')).toBe('—')
  })
})

describe('formatDuration', () => {
  it('returns an em dash for negative or non-finite input', () => {
    expect(formatDuration(-1)).toBe('—')
    expect(formatDuration(NaN)).toBe('—')
    expect(formatDuration(undefined)).toBe('—')
  })

  it('formats milliseconds below one second', () => {
    expect(formatDuration(0)).toBe('0 ms')
    expect(formatDuration(999)).toBe('999 ms')
    expect(formatDuration(123.6)).toBe('124 ms')
  })

  it('formats seconds', () => {
    expect(formatDuration(1000)).toBe('1.0 s')
    expect(formatDuration(1500)).toBe('1.5 s')
  })

  it('formats minutes and hours', () => {
    expect(formatDuration(61000)).toBe('1 m 1 s')
    expect(formatDuration(3600000)).toBe('1 h 0 m')
    expect(formatDuration(3900000)).toBe('1 h 5 m')
  })
})

describe('formatPercent', () => {
  it('formats a ratio as percent', () => {
    expect(formatPercent(1, 4)).toBe('25%')
    expect(formatPercent(1, 4, 2)).toBe('25.00%')
    expect(formatPercent(3, 4)).toBe('75%')
  })

  it('returns an empty string for invalid totals', () => {
    expect(formatPercent(1, 0)).toBe('')
    expect(formatPercent(1, -5)).toBe('')
    expect(formatPercent(NaN, 10)).toBe('')
    expect(formatPercent(10, NaN)).toBe('')
    expect(formatPercent(undefined, 10)).toBe('')
  })
})
