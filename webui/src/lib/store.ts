import { createStore } from 'zustand/vanilla'
import { useStore } from 'zustand'
import type { ChatMsg, NoxBackendState, ServerEvent } from './types'

export interface NoxState {
  conn: 'connecting' | 'open' | 'closed'
  state: NoxBackendState
  muted: boolean
  devTools: boolean
  setupComplete: boolean | null
  chat: ChatMsg[]
  level: number
}

export const initialState: NoxState = {
  conn: 'connecting',
  state: 'INITIALISING',
  muted: false,
  devTools: false,
  setupComplete: null,
  chat: [],
  level: 0,
}

const CHAT_CAP = 500

export const store = createStore<NoxState>(() => ({ ...initialState }))

export function applyEvent(ev: ServerEvent): void {
  const s = store.getState()
  switch (ev.t) {
    case 'hello':
      store.setState({
        state: ev.state, muted: ev.muted, devTools: ev.dev_tools,
        setupComplete: ev.setup_complete, chat: ev.history,
      })
      break
    case 'state':
      store.setState({ state: ev.state })
      break
    case 'chat': {
      const next = [...s.chat, ev]
      store.setState({ chat: next.length > CHAT_CAP ? next.slice(-CHAT_CAP) : next })
      break
    }
    case 'mute':
      store.setState({ muted: ev.muted })
      break
    case 'viz':
      store.setState({ level: ev.level })
      break
    case 'dev_tools':
      store.setState({ devTools: ev.enabled })
      break
    case 'tool': {
      const text = `⚙ ${ev.name} ${ev.status}${ev.ms != null ? ` · ${ev.ms}ms` : ''}`
      const next = [...s.chat, { t: 'chat', role: 'sys', text } as const]
      store.setState({ chat: next.length > CHAT_CAP ? next.slice(-CHAT_CAP) : next })
      break
    }
  }
}

export function setConn(conn: NoxState['conn']): void {
  store.setState({ conn })
}

export function useNox<T>(selector: (s: NoxState) => T): T {
  return useStore(store, selector)
}
