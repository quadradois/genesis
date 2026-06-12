import { applyEvent, setConn, store } from './store'
import type { ServerEvent } from './types'

const BACKOFF_MS = [500, 1000, 2000, 4000, 8000]
let ws: WebSocket | null = null
let attempt = 0

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
  setConn('connecting')
  ws = new WebSocket(wsUrl())
  ws.onopen = () => {
    attempt = 0
    setConn('open')
  }
  ws.onmessage = (e) => {
    try {
      applyEvent(JSON.parse(e.data) as ServerEvent)
    } catch { /* frame inválido: ignora */ }
  }
  ws.onclose = () => {
    setConn('closed')
    const delay = BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]
    attempt += 1
    setTimeout(connect, delay)
  }
  ws.onerror = () => ws?.close()
}

function send(obj: unknown): void {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj))
}

export function sendMessage(text: string): void {
  send({ t: 'message', text })
}

export function sendMute(muted: boolean): void {
  send({ t: 'mute', muted })
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
