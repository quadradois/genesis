// Palco do cérebro: usa 3D (R3F) quando WebGL existe; senão cai no canvas 2D do M1.
import { useState } from 'react'
import Brain2D from '../Brain'
import Brain3D from './Brain3D'
import { useNox } from '../../lib/store'

function hasWebGL(): boolean {
  try {
    const cv = document.createElement('canvas')
    return !!(cv.getContext('webgl2') || cv.getContext('webgl'))
  } catch {
    return false
  }
}

export default function BrainStage() {
  const [webgl] = useState(hasWebGL)
  const muted = useNox(s => s.muted)
  if (!webgl) return <Brain2D />
  return (
    <div className={`relative h-full w-full transition-opacity duration-500 ${muted ? 'opacity-50' : 'opacity-100'}`}>
      <Brain3D />
      {muted && (
        <div className="absolute inset-x-0 bottom-2 text-center text-xs tracking-[0.3em] text-rose-400/80">
          MICROFONE MUDO
        </div>
      )}
    </div>
  )
}
