import { ref, onUnmounted } from 'vue'

export interface WebSocketOptions {
  onMessage?: (data: any) => void
  reconnectInterval?: number
}

export function useWebSocket(path: string, options: WebSocketOptions = {}) {
  const reconnectInterval = options.reconnectInterval ?? 2000
  const isConnected = ref(false)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let shouldReconnect = true

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${proto}//${location.host}${path}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      isConnected.value = true
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        options.onMessage?.(data)
      } catch (err) {
        console.error('Failed to parse WebSocket message', err)
      }
    }

    ws.onclose = () => {
      isConnected.value = false
      if (shouldReconnect) {
        reconnectTimer = setTimeout(connect, reconnectInterval)
      }
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function send(message: any) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
    }
  }

  function disconnect() {
    shouldReconnect = false
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (ws) {
      ws.onclose = null
      ws.close()
    }
  }

  connect()
  onUnmounted(disconnect)

  return { isConnected, send, disconnect }
}
