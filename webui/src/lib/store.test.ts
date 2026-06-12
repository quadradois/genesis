import { beforeEach, describe, expect, it } from 'vitest'
import { store, applyEvent, initialState } from './store'
import { mapStateToMode } from './types'

describe('store', () => {
  beforeEach(() => store.setState({ ...initialState }, true))

  it('hello hidrata snapshot completo', () => {
    applyEvent({
      t: 'hello', state: 'LISTENING', muted: false, dev_tools: true,
      setup_complete: true, history: [{ t: 'chat', role: 'sys', text: 'NOX online.' }],
    })
    const s = store.getState()
    expect(s.state).toBe('LISTENING')
    expect(s.devTools).toBe(true)
    expect(s.setupComplete).toBe(true)
    expect(s.chat).toHaveLength(1)
  })

  it('chat acumula e state atualiza', () => {
    applyEvent({ t: 'chat', role: 'user', text: 'oi' })
    applyEvent({ t: 'chat', role: 'nox', text: 'olá' })
    applyEvent({ t: 'state', state: 'THINKING' })
    const s = store.getState()
    expect(s.chat.map(c => c.role)).toEqual(['user', 'nox'])
    expect(s.state).toBe('THINKING')
  })

  it('mute e viz atualizam campos', () => {
    applyEvent({ t: 'mute', muted: true })
    applyEvent({ t: 'viz', level: 0.7 })
    expect(store.getState().muted).toBe(true)
    expect(store.getState().level).toBe(0.7)
  })

  it('chat respeita o teto de 500 mensagens', () => {
    for (let i = 0; i < 510; i++) applyEvent({ t: 'chat', role: 'sys', text: `m${i}` })
    const chat = store.getState().chat
    expect(chat).toHaveLength(500)
    expect(chat[0].text).toBe('m10')
    expect(chat[499].text).toBe('m509')
  })

  it('tool com ms=0 renderiza sufixo', () => {
    applyEvent({ t: 'tool', name: 'x', status: 'ok', ms: 0 })
    expect(store.getState().chat[0].text).toBe('⚙ x ok · 0ms')
  })
})

describe('mapStateToMode', () => {
  it('mapeia estados do backend para modos do cérebro', () => {
    expect(mapStateToMode('SPEAKING')).toBe('speak')
    expect(mapStateToMode('THINKING')).toBe('think')
    expect(mapStateToMode('LISTENING')).toBe('idle')
    expect(mapStateToMode('MUTED')).toBe('idle')
    expect(mapStateToMode('INITIALISING')).toBe('idle')
  })
})
