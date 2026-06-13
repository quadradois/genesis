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

interface Part {
  obj: SPEObject
  rx: number
  ry: number
  rz: number
  py: number
}

function grab(objs: SPEObject[], names: string[]): Part | null {
  for (const n of names) {
    const o = objs.find(x => x.name === n)
    if (o) return { obj: o, rx: o.rotation.x, ry: o.rotation.y, rz: o.rotation.z, py: o.position.y }
  }
  return null
}

export default function RobotStage() {
  const state = useNox(s => s.state)
  const muted = useNox(s => s.muted)
  const mode = mapStateToMode(state)
  const modeRef = useRef(mode)
  modeRef.current = mode
  const glowRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<HTMLDivElement>(null)
  const partsRef = useRef<{ head: Part | null; hand: Part | null; body: Part | null }>({
    head: null, hand: null, body: null,
  })

  const handleLoad = (app: Application) => {
    try {
      const objs: SPEObject[] = (app as unknown as { getAllObjects?: () => SPEObject[] }).getAllObjects?.() ?? []
      console.log('[NOX] objetos da cena Spline:', objs.map(o => o.name))
      // Partes descobertas ao inspecionar a cena: Head, Hand, Body/fusedBody.
      partsRef.current = {
        head: grab(objs, ['Head', 'head', 'Cabeca']),
        hand: grab(objs, ['Hand', 'hand', 'Arm', 'arm']),
        body: grab(objs, ['Body', 'fusedBody', 'body', 'Bot', 'nexbot', 'Robot']),
      }
      const found = Object.entries(partsRef.current)
        .filter(([, v]) => v).map(([k]) => k)
      console.log('[NOX] marionete ativa nas partes:', found.length ? found.join(', ') : 'nenhuma (usando só glow)')
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

      // marionete por partes (sem brigar com o "olhar segue mouse" nativo)
      const { head, hand, body } = partsRef.current
      try {
        if (m === 'speak') {
          // cabeça acena no ritmo da voz; corpo respira rápido; mão gesticula leve
          if (head) {
            head.obj.rotation.x = head.rx + Math.sin(t * 9) * 0.06 * (0.4 + env)
            head.obj.rotation.z = head.rz + Math.sin(t * 2.1) * 0.03
          }
          if (body) body.obj.position.y = body.py + Math.sin(t * 9) * 6 * env
          if (hand) hand.obj.rotation.z = hand.rz + Math.sin(t * 5.5) * 0.12 * (0.3 + env)
        } else if (m === 'think') {
          // cabeça inclina pensativa e varre devagar; mão sobe ao "queixo"
          if (head) {
            head.obj.rotation.y = head.ry + Math.sin(t * 0.9) * 0.18
            head.obj.rotation.z = head.rz + 0.12
          }
          if (body) body.obj.position.y = body.py + Math.sin(t * 2.6) * 2
          if (hand) hand.obj.rotation.z = hand.rz + 0.25
        } else {
          // ocioso: tudo volta ao repouso, respiração lenta
          if (head) {
            head.obj.rotation.x = head.rx
            head.obj.rotation.y = head.ry
            head.obj.rotation.z = head.rz
          }
          if (body) body.obj.position.y = body.py + Math.sin(t * 1.2) * 3
          if (hand) hand.obj.rotation.z = hand.rz
        }
      } catch { /* objeto descartado durante hot-reload: ignora */ }

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
