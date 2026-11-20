// Vitest setup for jsdom: polyfills needed by uPlot (canvas 2D context, Path2D,
// matchMedia, ResizeObserver). Kept dependency-free so CI does not need the
// native `canvas` build.
import { vi } from 'vitest'

/* ------------------------------------------------------------------ */
/* Path2D                                                              */
/* ------------------------------------------------------------------ */

if (typeof globalThis.Path2D === 'undefined') {
  class Path2D {
    constructor(_path?: unknown) {}
    addPath() {}
    closePath() {}
    moveTo() {}
    lineTo() {}
    quadraticCurveTo() {}
    bezierCurveTo() {}
    arc() {}
    arcTo() {}
    ellipse() {}
    rect() {}
    roundRect() {}
  }
  // @ts-expect-error - jsdom has no Path2D typings at runtime
  globalThis.Path2D = Path2D
}

/* ------------------------------------------------------------------ */
/* CanvasRenderingContext2D                                            */
/* ------------------------------------------------------------------ */

function createContext2D(canvas: HTMLCanvasElement) {
  const gradient = { addColorStop: vi.fn() }
  const pattern = { setTransform: vi.fn() }
  const imageData = { data: new Uint8ClampedArray(4), width: 1, height: 1 }

  return {
    canvas,
    // rectangles
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    clearRect: vi.fn(),
    // paths
    beginPath: vi.fn(),
    closePath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    bezierCurveTo: vi.fn(),
    quadraticCurveTo: vi.fn(),
    arc: vi.fn(),
    arcTo: vi.fn(),
    ellipse: vi.fn(),
    rect: vi.fn(),
    roundRect: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    clip: vi.fn(),
    isPointInPath: vi.fn(() => false),
    isPointInStroke: vi.fn(() => false),
    // text
    fillText: vi.fn(),
    strokeText: vi.fn(),
    measureText: vi.fn((text: string) => ({
      width: (text?.length ?? 0) * 6,
      actualBoundingBoxAscent: 8,
      actualBoundingBoxDescent: 2,
      actualBoundingBoxLeft: 0,
      actualBoundingBoxRight: (text?.length ?? 0) * 6,
    })),
    // images
    drawImage: vi.fn(),
    createImageData: vi.fn(() => imageData),
    getImageData: vi.fn(() => imageData),
    putImageData: vi.fn(),
    // gradients / patterns
    createLinearGradient: vi.fn(() => gradient),
    createRadialGradient: vi.fn(() => gradient),
    createConicGradient: vi.fn(() => gradient),
    createPattern: vi.fn(() => pattern),
    // transforms
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    scale: vi.fn(),
    rotate: vi.fn(),
    transform: vi.fn(),
    setTransform: vi.fn(),
    resetTransform: vi.fn(),
    // dashes
    setLineDash: vi.fn(),
    getLineDash: vi.fn(() => []),
    // style state
    globalAlpha: 1,
    globalCompositeOperation: 'source-over',
    font: '10px sans-serif',
    fillStyle: '#000000',
    strokeStyle: '#000000',
    lineWidth: 1,
    lineCap: 'butt',
    lineJoin: 'miter',
    miterLimit: 10,
    lineDashOffset: 0,
    textAlign: 'start',
    textBaseline: 'alphabetic',
    direction: 'ltr',
    shadowBlur: 0,
    shadowColor: 'rgba(0, 0, 0, 0)',
    shadowOffsetX: 0,
    shadowOffsetY: 0,
    filter: 'none',
  }
}

const originalGetContext = HTMLCanvasElement.prototype.getContext

HTMLCanvasElement.prototype.getContext = function getContext(
  this: HTMLCanvasElement,
  contextType: string,
  ...rest: unknown[]
) {
  if (contextType === '2d') {
    // Cache one context per canvas, like a real implementation.
    const cached = (this as unknown as { __ctx2d?: ReturnType<typeof createContext2D> }).__ctx2d
    if (cached) return cached
    const ctx = createContext2D(this)
    ;(this as unknown as { __ctx2d?: ReturnType<typeof createContext2D> }).__ctx2d = ctx
    return ctx as unknown as CanvasRenderingContext2D
  }
  // @ts-expect-error - passthrough for other context types (webgl, etc.)
  return originalGetContext ? originalGetContext.call(this, contextType, ...rest) : null
} as typeof HTMLCanvasElement.prototype.getContext

/* ------------------------------------------------------------------ */
/* Browser APIs missing from jsdom                                     */
/* ------------------------------------------------------------------ */

if (typeof window !== 'undefined') {
  if (!window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  }

  if (!('ResizeObserver' in window)) {
    ;(window as unknown as { ResizeObserver: unknown }).ResizeObserver = vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
    }))
  }

  if (!('IntersectionObserver' in window)) {
    ;(window as unknown as { IntersectionObserver: unknown }).IntersectionObserver = vi.fn().mockImplementation(() => ({
      observe: vi.fn(),
      unobserve: vi.fn(),
      disconnect: vi.fn(),
      takeRecords: vi.fn(() => []),
    }))
  }

  if (!window.devicePixelRatio) {
    Object.defineProperty(window, 'devicePixelRatio', { writable: true, value: 1 })
  }
}
