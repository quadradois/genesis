import { useEffect, useState, type ReactNode } from 'react'
import { useNox } from '../lib/store'
import { authHeaders } from '../lib/ws'

export default function SetupGate({ children }: { children: ReactNode }) {
  const setupComplete = useNox(s => s.setupComplete)
  const [gemini, setGemini] = useState('')
  const [openrouter, setOpenrouter] = useState('')
  const [osName, setOsName] = useState('windows')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => { setSaved(false) }, [setupComplete])

  if (setupComplete !== false || saved) return <>{children}</>

  const submit = async () => {
    if (!gemini.trim() && !openrouter.trim()) return
    setSaving(true)
    const r = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ gemini_api_key: gemini, openrouter_api_key: openrouter, os_system: osName }),
    })
    setSaving(false)
    if (r.ok) setSaved(true)
  }

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-[#14304a] bg-[#0a1626]/80 p-6 backdrop-blur">
        <h1 className="mb-1 text-lg font-semibold tracking-[0.4em] text-cyan-300">N O X</h1>
        <p className="mb-5 text-sm text-slate-400">Primeira execução: configure as chaves de API.</p>
        <label className="mb-1 block text-xs uppercase tracking-wider text-slate-500">Gemini API key</label>
        <input value={gemini} onChange={e => setGemini(e.target.value)} type="password"
          className="mb-3 w-full rounded-lg border border-[#14304a] bg-[#061021] px-3 py-2 text-sm outline-none focus:border-cyan-600/60" />
        <label className="mb-1 block text-xs uppercase tracking-wider text-slate-500">OpenRouter API key (opcional)</label>
        <input value={openrouter} onChange={e => setOpenrouter(e.target.value)} type="password"
          className="mb-3 w-full rounded-lg border border-[#14304a] bg-[#061021] px-3 py-2 text-sm outline-none focus:border-cyan-600/60" />
        <label className="mb-1 block text-xs uppercase tracking-wider text-slate-500">Sistema operacional</label>
        <div className="mb-5 flex gap-2">
          {(['windows', 'mac', 'linux'] as const).map(o => (
            <button key={o} onClick={() => setOsName(o)}
              className={`flex-1 rounded-lg border px-2 py-1.5 text-sm capitalize transition ${
                osName === o ? 'border-cyan-500/70 bg-cyan-950/40 text-cyan-200' : 'border-[#14304a] text-slate-400'
              }`}>{o}</button>
          ))}
        </div>
        <button onClick={submit} disabled={saving || (!gemini.trim() && !openrouter.trim())}
          className="w-full rounded-lg bg-gradient-to-r from-cyan-500 to-indigo-500 py-2 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-40">
          {saving ? 'Salvando…' : 'Iniciar NOX'}
        </button>
      </div>
    </div>
  )
}
