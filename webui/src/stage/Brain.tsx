import { useEffect, useRef } from 'react'
import { createBrain, type BrainHandle } from './brainCanvas'
import { useNox } from '../lib/store'
import { mapStateToMode } from '../lib/types'

export default function Brain() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const handleRef = useRef<BrainHandle | null>(null)
  const state = useNox(s => s.state)
  const muted = useNox(s => s.muted)
  const level = useNox(s => s.level)

  useEffect(() => {
    if (!canvasRef.current) return
    handleRef.current = createBrain(canvasRef.current)
    return () => handleRef.current?.destroy()
  }, [])

  useEffect(() => { handleRef.current?.setMode(mapStateToMode(state)) }, [state])
  useEffect(() => { handleRef.current?.setLevel(level) }, [level])

  return (
    <div className={`relative h-full w-full transition-opacity duration-500 ${muted ? 'opacity-50' : 'opacity-100'}`}>
      <canvas ref={canvasRef} className="block h-full w-full" />
      {muted && (
        <div className="absolute inset-x-0 bottom-2 text-center text-xs tracking-[0.3em] text-rose-400/80">
          MICROFONE MUDO
        </div>
      )}
    </div>
  )
}
