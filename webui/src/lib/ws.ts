import { applyEvent, setConn, store } from './store'
import type { ServerEvent } from './types'

const BACKOFF_MS = [500, 1000, 2000, 4000, 8000]
let ws: WebSocket | null = null
let attempt = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let binaryHandler: ((data: ArrayBuffer) => void) | null = null
let serverEventHandler: ((ev: ServerEvent) => void) | null = null

export function getToken(): string | null {
  const fromUrl = new URLSearchParams(location.search).get('token')
  if (fromUrl) {
    localStorage.setItem('nox_token', fromUrl)
    return fromUrl
  }
  return localStorage.getItem('nox_token')
}

function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = getToken()
  return `${proto}://${location.host}/ws${token ? `?token=${token}` : ''}`
}

export function connect(): void {
  // Guard de reentrância: StrictMode (dev) monta efeitos 2x.
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) return
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  setConn('connecting')
  const sock = new WebSocket(wsUrl())
  sock.binaryType = 'arraybuffer'
  ws = sock
  sock.onopen = () => {
    attempt = 0
    setConn('open')
  }
  sock.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) {
      binaryHandler?.(e.data)
      return
    }
    try {
      const ev = JSON.parse(e.data) as ServerEvent
      applyEvent(ev)
      serverEventHandler?.(ev)
    } catch { /* frame inválido: ignora */ }
  }
  sock.onclose = () => {
    if (ws !== sock) return // socket substituído: ignora eventos do antigo
    setConn('closed')
    const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
    attempt += 1
    if (reconnectTimer) clearTimeout(reconnectTimer)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }
  sock.onerror = () => sock.close()
}

function send(obj: unknown): void {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj))
}

export function sendBinary(data: ArrayBuffer): void {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(data)
}

export function setBinaryHandler(handler: ((data: ArrayBuffer) => void) | null): void {
  binaryHandler = handler
}

export function setServerEventHandler(handler: ((ev: ServerEvent) => void) | null): void {
  serverEventHandler = handler
}

export function sendMessage(text: string): void {
  send({ t: 'message', text })
}

export function sendMute(muted: boolean): void {
  send({ t: 'mute', muted })
}

export function sendAudioSource(source: 'pc' | 'phone'): void {
  send({ t: 'audio_source', source })
}

export function sendDevTools(enabled: boolean): void {
  send({ t: 'dev_tools', enabled })
}

export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { 'x-nox-token': token } : {}
}

// referência usada pelo upload (Task 10) para evitar import circular
export { store as noxStore }
