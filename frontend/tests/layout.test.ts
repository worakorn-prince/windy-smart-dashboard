import { beforeEach, describe, expect, it } from 'vitest'
import {
  CARD_DEFS,
  LAYOUT_STORAGE_KEY,
  canMoveCard,
  defaultLayout,
  loadLayout,
  moveCard,
  resetLayout,
  saveLayout,
  toggleHidden,
} from '@/composables/useLayout'
import type { LayoutState } from '@/composables/useLayout'

const ALL_IDS = CARD_DEFS.map((def) => def.id)
const SECONDARY_IDS = CARD_DEFS.filter((def) => def.zone === 'secondary').map((def) => def.id)

// Node 22 exposes an unusable global localStorage, so jsdom's one is missing here.
// Install a minimal in-memory Storage before the composable reads the global.
function createMemoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear() {
      data.clear()
    },
    getItem(key: string) {
      return data.has(key) ? (data.get(key) as string) : null
    },
    key(index: number) {
      return Array.from(data.keys())[index] ?? null
    },
    removeItem(key: string) {
      data.delete(key)
    },
    setItem(key: string, value: string) {
      data.set(key, String(value))
    },
  } as Storage
}

function installLocalStorage(): Storage {
  const existing = (globalThis as { localStorage?: Storage }).localStorage
  if (existing && typeof existing.getItem === 'function') return existing

  const storage = createMemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true, writable: true })
  const win = (globalThis as { window?: { localStorage?: Storage } }).window
  if (win) {
    Object.defineProperty(win, 'localStorage', { value: storage, configurable: true, writable: true })
  }
  return storage
}

const storage = installLocalStorage()

function idsInZone(state: LayoutState, zone: string): string[] {
  return state.order.filter((id) => CARD_DEFS.find((def) => def.id === id)?.zone === zone)
}

beforeEach(() => {
  storage.clear()
})

describe('defaultLayout', () => {
  it('contains every card exactly once in definition order', () => {
    const state = defaultLayout()

    expect(state.order).toEqual(ALL_IDS)
    expect(new Set(state.order).size).toBe(CARD_DEFS.length)
    expect(state.hidden).toEqual([])
  })

  it('is used by loadLayout when nothing is stored', () => {
    expect(loadLayout()).toEqual(defaultLayout())
  })
})

describe('moveCard', () => {
  it('swaps with the next card in the same zone', () => {
    const base = defaultLayout()
    const moved = moveCard(base, 'cpu', 1)
    const expected = [...base.order]
    const index = expected.indexOf('cpu')
    const neighbour = expected[index + 1]
    expected[index + 1] = expected[index]
    expected[index] = neighbour

    expect(moved.order).toEqual(expected)
    expect(moved.order.indexOf('cpu')).toBe(base.order.indexOf('cpu') + 1)
  })

  it('swaps with the previous card in the same zone', () => {
    const base = defaultLayout()
    const moved = moveCard(base, 'gpu', -1)

    expect(moved.order.indexOf('gpu')).toBe(base.order.indexOf('gpu') - 1)
    expect(idsInZone(moved, 'primary')).toEqual(['cpu', 'gpu', 'ram'])
  })

  it('does not cross zone boundaries', () => {
    const base = defaultLayout()

    expect(moveCard(base, 'cpu', -1).order).toEqual(base.order)
    expect(moveCard(base, 'speedtest', 1).order).toEqual(base.order)
    expect(moveCard(base, 'adapters', 1).order).toEqual(base.order)
  })

  it('returns a new state and never mutates its input', () => {
    const base = defaultLayout()
    const snapshot = [...base.order]
    const moved = moveCard(base, 'ram', 1)

    expect(moved).not.toBe(base)
    expect(moved.order).not.toBe(base.order)
    expect(base.order).toEqual(snapshot)
  })

  it('ignores unknown ids', () => {
    const base = defaultLayout()
    const moved = moveCard(base, 'does-not-exist', 1)

    expect(moved).not.toBe(base)
    expect(moved.order).toEqual(base.order)
  })

  it('reports movable neighbours with canMoveCard', () => {
    const base = defaultLayout()

    expect(canMoveCard(base, 'cpu', 1)).toBe(true)
    expect(canMoveCard(base, 'cpu', -1)).toBe(false)
    expect(canMoveCard(base, 'adapters', 1)).toBe(false)
    expect(canMoveCard(base, 'unknown', 1)).toBe(false)
  })
})

describe('toggleHidden', () => {
  it('hides and shows a card again', () => {
    const base = defaultLayout()
    const hidden = toggleHidden(base, 'cpu')

    expect(hidden.hidden).toEqual(['cpu'])
    expect(base.hidden).toEqual([])

    const shown = toggleHidden(hidden, 'cpu')
    expect(shown.hidden).toEqual([])
  })

  it('refuses to hide the last visible card of a zone', () => {
    let state = defaultLayout()
    for (const id of SECONDARY_IDS.slice(0, -1)) {
      state = toggleHidden(state, id)
    }

    expect(state.hidden).toHaveLength(SECONDARY_IDS.length - 1)
    expect(idsInZone(state, 'secondary').filter((id) => !state.hidden.includes(id))).toHaveLength(1)

    const last = SECONDARY_IDS[SECONDARY_IDS.length - 1]
    const attempted = toggleHidden(state, last)

    expect(attempted.hidden).toEqual(state.hidden)
    expect(attempted).not.toBe(state)
  })

  it('ignores unknown ids', () => {
    const base = defaultLayout()
    const next = toggleHidden(base, 'nope')

    expect(next.hidden).toEqual([])
    expect(next.order).toEqual(base.order)
  })

  it('does not count optional cards when guarding the last visible card', () => {
    let state = defaultLayout()
    for (const id of ['power', 'disk', 'network', 'system']) {
      state = toggleHidden(state, id)
    }

    expect(state.hidden).toEqual(['power', 'disk', 'network', 'system'])
    expect(state.hidden).not.toContain('battery')

    const attempted = toggleHidden(state, 'speedtest')

    expect(attempted.hidden).toEqual(state.hidden)
  })

  it('allows hiding optional cards freely', () => {
    const hidden = toggleHidden(defaultLayout(), 'battery')

    expect(hidden.hidden).toEqual(['battery'])
    expect(idsInZone(hidden, 'secondary').filter((id) => !hidden.hidden.includes(id)).length).toBeGreaterThan(0)
  })
})

describe('loadLayout', () => {
  it('drops unknown ids and appends new cards at the end of their zone', () => {
    storage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({
        order: ALL_IDS.filter((id) => id !== 'adapters'),
        hidden: ['gpu', 'ghost-card'],
      }),
    )

    const loaded = loadLayout()

    expect(loaded.order).not.toContain('ghost-card')
    expect(loaded.order.slice(-3)).toEqual(['history', 'processes', 'adapters'])
    expect(loaded.order).toHaveLength(CARD_DEFS.length)
    expect(loaded.hidden).toEqual(['gpu'])
  })

  it('keeps stored order and places missing cards after their zone neighbours', () => {
    storage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({ order: ['ram', 'cpu', 'ghost'], hidden: [] }),
    )

    const loaded = loadLayout()

    expect(loaded.order.slice(0, 3)).toEqual(['ram', 'cpu', 'gpu'])
    expect(new Set(loaded.order).size).toBe(CARD_DEFS.length)
    expect(loaded.order).toHaveLength(CARD_DEFS.length)
  })

  it('deduplicates repeated ids', () => {
    storage.setItem(
      LAYOUT_STORAGE_KEY,
      JSON.stringify({ order: ['cpu', 'cpu', ...ALL_IDS.filter((id) => id !== 'cpu')], hidden: ['cpu', 'cpu'] }),
    )

    const loaded = loadLayout()

    expect(loaded.order.filter((id) => id === 'cpu')).toHaveLength(1)
    expect(loaded.hidden).toEqual(['cpu'])
    expect(loaded.order).toHaveLength(CARD_DEFS.length)
  })

  it('falls back to the default layout for broken or null JSON', () => {
    storage.setItem(LAYOUT_STORAGE_KEY, '{not json')
    expect(loadLayout()).toEqual(defaultLayout())

    storage.setItem(LAYOUT_STORAGE_KEY, 'null')
    expect(loadLayout()).toEqual(defaultLayout())

    storage.setItem(LAYOUT_STORAGE_KEY, '[]')
    expect(loadLayout()).toEqual(defaultLayout())
  })

  it('keeps an optional card hidden when a required card is still visible', () => {
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({ order: ALL_IDS, hidden: ['battery'] }))

    expect(loadLayout().hidden).toEqual(['battery'])
  })

  it('unhides the first required card of a zone that would otherwise be empty', () => {
    const secondaryIds = CARD_DEFS.filter((def) => def.zone === 'secondary').map((def) => def.id)
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({ order: ALL_IDS, hidden: secondaryIds }))

    const loaded = loadLayout()
    const requiredSecondary = CARD_DEFS.filter((def) => def.zone === 'secondary' && !def.optional).map((def) => def.id)

    expect(loaded.hidden).not.toContain(requiredSecondary[0])
    expect(requiredSecondary.slice(1).every((id) => loaded.hidden.includes(id))).toBe(true)
    expect(loaded.hidden).toContain('battery')
    expect(loaded.hidden).toContain('speedtest')
  })
})

describe('saveLayout / resetLayout', () => {
  it('round-trips a layout through localStorage', () => {
    const changed = moveCard(toggleHidden(defaultLayout(), 'disk'), 'gpu', -1)
    saveLayout(changed)

    expect(loadLayout()).toEqual(changed)
  })

  it('resetLayout clears the stored key and returns the default layout', () => {
    saveLayout({ order: ['gpu'], hidden: ['cpu'] })
    expect(storage.getItem(LAYOUT_STORAGE_KEY)).not.toBeNull()

    const reset = resetLayout()

    expect(storage.getItem(LAYOUT_STORAGE_KEY)).toBeNull()
    expect(reset).toEqual(defaultLayout())
  })
})
