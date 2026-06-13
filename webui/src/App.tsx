import { useEffect } from 'react'
import { motion } from 'framer-motion'
import Brain from './stage/brain3d'
import ChatPanel from './chat/ChatPanel'
import Composer from './chat/Composer'
import SetupGate from './settings/SetupGate'
import { SplineSceneBasic } from './components/spline-demo'
import { connect } from './lib/ws'
import { useNox } from './lib/store'

// ?stage=spline → demo Spline (comparação de direção visual); padrão = cérebro 3D
const STAGE_MODE = new URLSearchParams(window.location.search).get('stage')

function ConnBadge() {
  const conn = useNox(s => s.conn)
  const color = conn === 'open' ? 'bg-emerald-400' : conn === 'connecting' ? 'bg-amber-400' : 'bg-rose-500'
  const label = conn === 'open' ? 'online' : conn === 'connecting' ? 'conectando' : 'reconectando'
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-slate-400">
      <span className={`h-2 w-2 rounded-full ${color}`} /> {label}
    </span>
  )
}

function StateBadge() {
  const state = useNox(s => s.state)
  return <span className="text-[11px] tracking-[0.25em] text-cyan-500/80">{state}</span>
}

export default function App() {
  useEffect(() => { connect() }, [])
  const hasChat = useNox(s => s.chat.some(m => m.role === 'user' || m.role === 'nox'))

  return (
    <SetupGate>
      <div className="flex h-full flex-col">
        <header className="flex items-center justify-between border-b border-[#14304a] px-4 py-2">
          <h1 className="text-sm font-semibold tracking-[0.5em] text-cyan-300">N O X</h1>
          <div className="flex items-center gap-4">
            <StateBadge />
            <ConnBadge />
          </div>
        </header>
        <motion.div
          layout
          animate={{ flexBasis: hasChat ? '42%' : '100%' }}
          transition={{ type: 'spring', stiffness: 120, damping: 22 }}
          className="min-h-[220px] shrink-0 grow-0"
          style={{ flexBasis: '100%' }}
        >
          {STAGE_MODE === 'spline' ? (
            <div className="h-full w-full p-3">
              <SplineSceneBasic />
            </div>
          ) : (
            <Brain />
          )}
        </motion.div>
        {hasChat && (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="min-h-0 flex-1"
          >
            <ChatPanel />
          </motion.div>
        )}
        <Composer />
      </div>
    </SetupGate>
  )
}
