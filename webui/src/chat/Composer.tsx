import { useEffect, useState } from 'react'
import { useNox } from '../lib/store'
import { sendMessage, sendMute, authHeaders } from '../lib/ws'
import { startMobileVoice, stopMobileVoice } from '../lib/mobileAudio'

export default function Composer() {
  const [text, setText] = useState('')
  const conn = useNox(s => s.conn)
  const muted = useNox(s => s.muted)
  const audioSource = useNox(s => s.audioSource)
  const [voiceBusy, setVoiceBusy] = useState(false)

  useEffect(() => () => stopMobileVoice(), [])

  const submit = () => {
    const t = text.trim()
    if (!t || conn !== 'open') return
    sendMessage(t)
    setText('')
  }

  const upload = async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch('/api/upload', { method: 'POST', body: fd, headers: authHeaders() })
    if (!r.ok) console.error('[NOX] upload falhou:', r.status)
  }

  const togglePhoneVoice = async () => {
    if (conn !== 'open' || voiceBusy) return
    setVoiceBusy(true)
    try {
      if (audioSource === 'phone') {
        stopMobileVoice()
      } else {
        await startMobileVoice()
      }
    } catch (e) {
      console.error('[NOX] voz mobile falhou:', e)
      alert(e instanceof Error ? e.message : 'Não foi possível ativar a voz mobile.')
    } finally {
      setVoiceBusy(false)
    }
  }

  return (
    <div className="nox-composer flex shrink-0 items-center gap-2 border-t border-[#14304a] bg-[#0a1626]/90 px-3 pt-2 backdrop-blur">
      <button
        onClick={() => sendMute(!muted)}
        title={muted ? 'Reativar microfone' : 'Silenciar microfone'}
        className={`h-9 w-9 shrink-0 rounded-lg border text-sm transition ${
          muted ? 'border-rose-500/60 text-rose-400' : 'border-emerald-500/50 text-emerald-300'
        }`}
      >
        {muted ? '🔇' : '🎙'}
      </button>
      <button
        onClick={togglePhoneVoice}
        disabled={conn !== 'open' || voiceBusy}
        title={audioSource === 'phone' ? 'Desativar voz do telefone' : 'Usar microfone e áudio deste telefone'}
        aria-pressed={audioSource === 'phone'}
        className={`h-10 w-10 shrink-0 rounded-lg border text-base transition disabled:opacity-40 ${
          audioSource === 'phone' ? 'border-cyan-400/70 bg-cyan-400/10 text-cyan-200' : 'border-[#234] text-slate-400 hover:text-cyan-200'
        }`}
      >
        {voiceBusy ? '…' : '☎'}
      </button>
      <label className="h-9 w-9 shrink-0 cursor-pointer rounded-lg border border-[#234] text-center text-sm leading-9 text-slate-400 hover:text-cyan-200">
        📎
        <input type="file" className="hidden" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
      </label>
      <input
        value={text}
        onChange={e => setText(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && submit()}
        placeholder={conn === 'open' ? 'Pergunte qualquer coisa…' : 'Reconectando…'}
        disabled={conn !== 'open'}
        className="h-9 flex-1 rounded-lg border border-[#14304a] bg-[#061021] px-3 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-600/60 disabled:opacity-50"
      />
      <button
        onClick={submit}
        disabled={conn !== 'open'}
        className="h-9 rounded-lg bg-gradient-to-r from-cyan-500 to-indigo-500 px-4 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-40"
      >
        ▸
      </button>
    </div>
  )
}
