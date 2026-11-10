export type CardZone = 'alerts' | 'primary' | 'secondary' | 'wide'

export interface CardDef {
  id: string
  title: string
  zone: CardZone
  optional?: boolean
}

export const CARD_DEFS: CardDef[] = [
  { id: 'alerts', title: 'Alerts', zone: 'alerts' },
  { id: 'alert-rules', title: 'Alert Rules', zone: 'alerts' },
  { id: 'cpu', title: 'CPU', zone: 'primary' },
  { id: 'ram', title: 'Memory', zone: 'primary' },
  { id: 'gpu', title: 'GPU', zone: 'primary' },
  { id: 'power', title: 'Power Usage', zone: 'secondary' },
  { id: 'battery', title: 'Battery', zone: 'secondary', optional: true },
  { id: 'disk', title: 'Storage', zone: 'secondary' },
  { id: 'network', title: 'Network', zone: 'secondary' },
  { id: 'system', title: 'System', zone: 'secondary' },
  { id: 'speedtest', title: 'Internet Speed Test', zone: 'secondary' },
  { id: 'history', title: 'History', zone: 'wide' },
  { id: 'processes', title: 'Top Processes', zone: 'wide' },
  { id: 'adapters', title: 'Network Adapters', zone: 'wide' },
]

export interface LayoutState {
  order: string[]
  hidden: string[]
}

export const LAYOUT_STORAGE_KEY = 'dash:layout:v1'

const ZONES: CardZone[] = ['alerts', 'primary', 'secondary', 'wide']

const CARD_BY_ID: Record<string, CardDef> = CARD_DEFS.reduce<Record<string, CardDef>>((acc, def) => {
  acc[def.id] = def
  return acc
}, {})

export function zoneOf(id: string): CardZone | null {
  return CARD_BY_ID[id]?.zone ?? null
}

export function isOptionalCard(id: string): boolean {
  return Boolean(CARD_BY_ID[id]?.optional)
}

function requiredCardsInZone(order: string[], zone: CardZone): string[] {
  return order.filter((id) => zoneOf(id) === zone && !isOptionalCard(id))
}

function enforceZoneInvariant(order: string[], hidden: string[]): string[] {
  const next = [...hidden]
  for (const zone of ZONES) {
    const required = requiredCardsInZone(order, zone)
    if (!required.length) continue
    if (required.some((id) => !next.includes(id))) continue

    const first = required[0]
    const index = next.indexOf(first)
    if (index >= 0) next.splice(index, 1)
  }
  return next
}

export function defaultLayout(): LayoutState {
  return { order: CARD_DEFS.map((def) => def.id), hidden: [] }
}

function cloneLayout(state: LayoutState): LayoutState {
  return { order: [...state.order], hidden: [...state.hidden] }
}

function getStorage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

function mergeOrder(raw: unknown): string[] {
  const known = new Set(CARD_DEFS.map((def) => def.id))
  const seen = new Set<string>()
  const order: string[] = []

  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (typeof item !== 'string' || !known.has(item) || seen.has(item)) continue
      seen.add(item)
      order.push(item)
    }
  }

  for (const zone of ZONES) {
    const missing = CARD_DEFS.filter((def) => def.zone === zone && !seen.has(def.id)).map((def) => def.id)
    if (!missing.length) continue

    let insertAt = -1
    for (let i = order.length - 1; i >= 0; i -= 1) {
      if (zoneOf(order[i]) === zone) {
        insertAt = i + 1
        break
      }
    }

    if (insertAt === -1) order.push(...missing)
    else order.splice(insertAt, 0, ...missing)
    missing.forEach((id) => seen.add(id))
  }

  return order
}

function normalizeHidden(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const known = new Set(CARD_DEFS.map((def) => def.id))
  const hidden: string[] = []
  for (const item of raw) {
    if (typeof item !== 'string' || !known.has(item) || hidden.includes(item)) continue
    hidden.push(item)
  }
  return hidden
}

export function loadLayout(): LayoutState {
  const storage = getStorage()
  if (!storage) return defaultLayout()

  let raw: string | null = null
  try {
    raw = storage.getItem(LAYOUT_STORAGE_KEY)
  } catch {
    return defaultLayout()
  }
  if (!raw) return defaultLayout()

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return defaultLayout()
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return defaultLayout()

  const candidate = parsed as Partial<LayoutState>
  const order = mergeOrder(candidate.order)
  return { order, hidden: enforceZoneInvariant(order, normalizeHidden(candidate.hidden)) }
}

export function saveLayout(state: LayoutState): void {
  const storage = getStorage()
  if (!storage) return
  try {
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({ order: [...state.order], hidden: [...state.hidden] }))
  } catch {
    // storage unavailable or quota exceeded — layout stays in memory
  }
}

export function resetLayout(): LayoutState {
  const storage = getStorage()
  if (storage) {
    try {
      storage.removeItem(LAYOUT_STORAGE_KEY)
    } catch {
      // ignore storage errors, still return the default layout
    }
  }
  return defaultLayout()
}

export function canMoveCard(state: LayoutState, id: string, dir: -1 | 1): boolean {
  const zone = zoneOf(id)
  const index = state.order.indexOf(id)
  if (!zone || index < 0) return false

  for (let i = index + dir; i >= 0 && i < state.order.length; i += dir) {
    if (zoneOf(state.order[i]) === zone) return true
  }
  return false
}

export function moveCard(state: LayoutState, id: string, dir: -1 | 1): LayoutState {
  const next = cloneLayout(state)
  const zone = zoneOf(id)
  const index = next.order.indexOf(id)
  if (!zone || index < 0) return next

  for (let i = index + dir; i >= 0 && i < next.order.length; i += dir) {
    if (zoneOf(next.order[i]) !== zone) continue
    next.order[index] = state.order[i]
    next.order[i] = state.order[index]
    return next
  }

  return next
}

export function toggleHidden(state: LayoutState, id: string): LayoutState {
  const next = cloneLayout(state)
  const zone = zoneOf(id)
  if (!zone) return next

  if (next.hidden.includes(id)) {
    next.hidden = next.hidden.filter((hiddenId) => hiddenId !== id)
    return next
  }

  if (!isOptionalCard(id)) {
    const remainingRequired = requiredCardsInZone(next.order, zone).filter(
      (cardId) => cardId !== id && !next.hidden.includes(cardId),
    )
    if (!remainingRequired.length) return next
  }

  next.hidden = [...next.hidden, id]
  return next
}
