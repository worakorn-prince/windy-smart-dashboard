/**
 * v-auto-tip — native tooltip appears only when the element's text is
 * actually clipped (ellipsis active). Keeps existing :title bindings
 * untouched; never overwrites a manually-set title.
 *
 * Usage: <span class="text-truncate" v-auto-tip>{{ longValue }}</span>
 */
import type { Directive } from 'vue'

function isClipped(el: HTMLElement): boolean {
  return el.scrollWidth > el.clientWidth + 1 ||
         el.scrollHeight > el.clientHeight + 1
}

function apply(el: HTMLElement) {
  // Respect explicit titles set via bindings or attributes.
  const owned = el.getAttribute('data-autotip-owned') === '1'
  if (!isClipped(el)) {
    if (owned) {
      el.removeAttribute('title')
      el.removeAttribute('data-autotip-owned')
    }
    return
  }
  if (el.hasAttribute('title') && !owned) return // manual title wins
  const text = el.getAttribute('data-fulltext') ?? el.textContent?.trim() ?? ''
  if (text) {
    el.setAttribute('title', text)
    el.setAttribute('data-autotip-owned', '1')
  }
}

export const autoTip: Directive<HTMLElement> = {
  mounted(el) {
    apply(el)
  },
  updated(el) {
    // Content changed (e.g. live metrics) — re-evaluate next frame so the
    // browser has laid out the new text first.
    requestAnimationFrame(() => apply(el))
  },
}
