import { ref } from 'vue'
import type { Ref } from 'vue'

export interface UseCardDragOptions {
  /** คืน card id ที่ pointer อยู่เหนือ (default: document.elementFromPoint + closest('[data-card-id]')) —
      ให้ injectable เพื่อ test ใน environment ที่ไม่มี layout (jsdom elementFromPoint คืน null) */
  resolveDropTarget?: (x: number, y: number) => string | null
  canSwap?: (fromId: string, toId: string) => boolean
  onSwap?: (fromId: string, toId: string) => void
}

export interface UseCardDrag {
  draggingId: Ref<string | null>
  dropTargetId: Ref<string | null>
  startDrag: (event: PointerEvent, cardId: string) => void
  stop: () => void
}

const DRAG_THRESHOLD_PX = 6

function defaultResolveDropTarget(x: number, y: number): string | null {
  const underPointer = document.elementFromPoint(x, y)
  if (!underPointer) return null
  const slot = underPointer.closest('[data-card-id]')
  return slot?.getAttribute('data-card-id') ?? null
}

export function useCardDrag(options: UseCardDragOptions): UseCardDrag {
  const draggingId = ref<string | null>(null)
  const dropTargetId = ref<string | null>(null)

  let active = false
  let dragging = false
  let captured = false
  let cardId: string | null = null
  let targetEl: Element | null = null
  let pointerId = -1
  let startX = 0
  let startY = 0

  function isSwapAllowed(fromId: string, toId: string): boolean {
    if (fromId === toId) return false
    return options.canSwap ? options.canSwap(fromId, toId) : true
  }

  function resolveDropTarget(x: number, y: number): string | null {
    if (!cardId) return null
    const resolve = options.resolveDropTarget ?? defaultResolveDropTarget
    const targetId = resolve(x, y)
    if (!targetId || !isSwapAllowed(cardId, targetId)) return null
    return targetId
  }

  function onPointerMove(event: Event) {
    if (!active) return
    const pointer = event as PointerEvent
    if (!dragging) {
      const dx = pointer.clientX - startX
      const dy = pointer.clientY - startY
      if (dx * dx + dy * dy < DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX) return
      dragging = true
      draggingId.value = cardId
    }
    dropTargetId.value = resolveDropTarget(pointer.clientX, pointer.clientY)
  }

  function onPointerUp() {
    if (!active) return
    const from = cardId
    const to = dropTargetId.value
    const completed = dragging
    resetState()
    if (completed && from && to) options.onSwap?.(from, to)
  }

  function onPointerCancel() {
    if (!active) return
    resetState()
  }

  function onKeyDown(event: KeyboardEvent) {
    if (!active) return
    if (event.key !== 'Escape') return
    resetState()
  }

  function resetState() {
    active = false
    dragging = false
    cardId = null
    captured = false
    draggingId.value = null
    dropTargetId.value = null
    if (targetEl) {
      targetEl.removeEventListener('pointermove', onPointerMove)
      targetEl.removeEventListener('pointerup', onPointerUp)
      targetEl.removeEventListener('pointercancel', onPointerCancel)
      if (captured) {
        try {
          targetEl.releasePointerCapture(pointerId)
        } catch {
          // pointer capture may already be released by the platform
        }
      }
    }
    targetEl = null
    document.removeEventListener('keydown', onKeyDown)
  }

  function startDrag(event: PointerEvent, id: string) {
    if (active) return
    const button = typeof event.button === 'number' ? event.button : 0
    if (button !== 0 && event.pointerType !== 'touch') return

    event.preventDefault()

    active = true
    dragging = false
    cardId = id
    draggingId.value = null
    dropTargetId.value = null
    startX = event.clientX
    startY = event.clientY
    pointerId = event.pointerId
    targetEl =
      (event.currentTarget as Element | null) ??
      (event.target instanceof Element ? event.target : null)

    if (targetEl) {
      const capture = targetEl.setPointerCapture?.bind(targetEl)
      if (capture) {
        try {
          capture(pointerId)
          captured = true
        } catch {
          captured = false
        }
      }
      targetEl.addEventListener('pointermove', onPointerMove)
      targetEl.addEventListener('pointerup', onPointerUp)
      targetEl.addEventListener('pointercancel', onPointerCancel)
    }
    document.addEventListener('keydown', onKeyDown)
  }

  function stop() {
    resetState()
  }

  return { draggingId, dropTargetId, startDrag, stop }
}
