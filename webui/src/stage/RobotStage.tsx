// Palco padrão do Nox: cena Spline (robô) com atmosfera E marionete reativas.
// Não dá para editar a cena hospedada, mas o runtime expõe os objetos — então
// além do glow/brilho, animamos o próprio robô por estado: respiração no ocioso,
// "olhando para os lados" no pensando, balanço no ritmo da voz ao falar.
// O nível de voz vem do store (eventos viz), lido via RAF — sem re-render.
import { useEffect, useRef } from 'react'
import type { Application, SPEObject } from '@splinetool/runtime'
import { SplineScene } from '@/components/ui/splite'
import { Spotlight } from '@/components/ui/spotlight'
import { store, useNox } from '../lib/store'
import { mapStateToMode } from '../lib/types'

const SCENE_URL = 'https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode'

interface Puppet {
  obj: SPEObject
  baseRotY: number
  baseRotZ: number
  basePosY: number
}

export default function RobotStage() {
  const state = useNox(s => s.state)
  const muted = useNox(s => s.muted)
  const mode = mapStateToMode(state)
  const modeRef = useRef(mode)
  modeRef.current = mode
  const glowRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<HTMLDivElement>(null)
  const puppetRef = useRef<Puppet | null>(null)

  const handleLoad = (app: Application) => {
    try {
      const objs: SPEObject[] = (app as unknown as { getAllObjects?: () => SPEObject[] }).getAllObjects?.() ?? []
      // Diagnóstico: abra o console (F12) para ver os nomes e me dizer qual animar
      console.log('[NOX] objetos da cena Spline:', objs.map(o => o.name))
      const prefer = ['nexbot', 'Nexbot', 'NEXBOT', 'robot', 'Robot', 'bot', 'Body', 'Group']
      let target: SPEObject | undefined
      for (const name of prefer) {
        target = objs.find(o => o.name === name)
        if (target) break
      }
      if (!target) target = objs[0]
      if (target) {
        puppetRef.current = {
          obj: target,
          baseRotY: target.rotation.y,
          baseRotZ: target.rotation.z,
          basePosY: target.position.y,
        }
        console.log('[NOX] marionete ativa no objeto:', target.name)
      }
    } catch (e) {
      console.warn('[NOX] cena sem marionete (runtime antigo?):', e)
    }
  }

  useEffect(() => {
    let raf = 0
    let env = 0
    let t = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      t += dt
      const lvl = store.getState().level
      const m = modeRef.current
      let target = 0
      if (m === 'speak') target = lvl > 0.01 ? Math.min(1, lvl) : 0.4 + 0.3 * Math.sin(t * 8)
      else if (m === 'think') target = 0.55 + 0.25 * Math.abs(Math.sin(t * 6))
      else target = Math.min(0.35, lvl) // reação sutil à voz do usuário
      env += (target - env) * Math.min(1, dt * 12)

      if (glowRef.current) {
        glowRef.current.style.opacity = String(0.25 + 0.55 * env)
        glowRef.current.style.transform = `translate(-50%, -50%) scale(${1 + 0.18 * env})`
      }
      if (sceneRef.current) {
        sceneRef.current.style.filter = `brightness(${1 + 0.22 * env}) saturate(${1 + 0.15 * env})`
      }

      // marionete: anima o objeto raiz do robô sem brigar com o "olhar segue mouse"
      const pup = puppetRef.current
      if (pup) {
        try {
          if (m === 'speak') {
            pup.obj.rotation.y = pup.baseRotY + Math.sin(t * 2.1) * 0.05
            pup.obj.rotation.z = pup.baseRotZ + Math.sin(t * 8.7) * 0.012 * (0.4 + env)
            pup.obj.position.y = pup.basePosY + Math.sin(t * 9) * 7 * env
          } else if (m === 'think') {
            pup.obj.rotation.y = pup.baseRotY + Math.sin(t * 0.9) * 0.16 // pondera, olha p/ os lados
            pup.obj.rotation.z = pup.baseRotZ
            pup.obj.position.y = pup.basePosY + Math.sin(t * 2.6) * 2
          } else {
            pup.obj.rotation.y = pup.baseRotY
            pup.obj.rotation.z = pup.baseRotZ
            pup.obj.position.y = pup.basePosY + Math.sin(t * 1.2) * 3 // respiração
          }
        } catch { /* objeto descartado durante hot-reload: ignora */ }
      }

      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  const glowColor = mode === 'think' ? 'rgba(255,140,66,0.5)' : 'rgba(34,211,238,0.45)'

  return (
    <div className={`relative h-full w-full overflow-hidden transition-opacity duration-500 ${muted ? 'opacity-50' : 'opacity-100'}`}>
      <Spotlight className="-top-40 left-0 md:left-60 md:-top-20" fill="white" />
      <div
        ref={glowRef}
        className="pointer-events-none absolute left-1/2 top-1/2 h-[70%] w-[60%] rounded-full blur-3xl"
        style={{
          background: `radial-gradient(circle, ${glowColor} 0%, transparent 70%)`,
          transform: 'translate(-50%, -50%)',
          opacity: 0.3,
        }}
      />
      <div ref={sceneRef} className="h-full w-full">
        <SplineScene scene={SCENE_URL} className="h-full w-full" onLoad={handleLoad} />
      </div>
      {muted && (
        <div className="absolute inset-x-0 bottom-2 text-center text-xs tracking-[0.3em] text-rose-400/80">
          MICROFONE MUDO
        </div>
      )}
    </div>
  )
}
