import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useNox } from '../lib/store'
import type { ChatMsg } from '../lib/types'

const STYLES: Record<ChatMsg['role'], string> = {
  user: 'self-end bg-[#16263d] text-slate-100 rounded-2xl rounded-br-md',
  nox: 'self-start bg-cyan-950/40 border border-cyan-800/40 text-cyan-100 rounded-2xl rounded-bl-md',
  sys: 'self-center text-[11px] text-slate-500 bg-transparent px-2 py-0.5',
  err: 'self-start bg-rose-950/40 border border-rose-800/50 text-rose-200 rounded-xl',
  file: 'self-center text-[12px] text-emerald-300/90 bg-emerald-950/30 border border-emerald-800/40 rounded-xl',
}

export default function ChatPanel() {
  const chat = useNox(s => s.chat)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat])

  return (
    <div className="flex h-full flex-col gap-2 overflow-y-auto px-4 py-3">
      {chat.map((m, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className={`max-w-[78%] px-3 py-2 text-sm leading-relaxed ${STYLES[m.role] ?? STYLES.sys}`}
        >
          {m.text}
        </motion.div>
      ))}
      <div ref={endRef} />
    </div>
  )
}
