// Cérebro neural 3D do Nox — React Three Fiber + bloom.
// Estados: idle (respiração) / think (morph + cascata) / speak (pulso pela voz real).
// O nível de voz chega via store (eventos `viz`) e é lido IMPERATIVAMENTE no
// frame loop — sem re-render React a 30Hz.
import { useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import * as THREE from 'three'
import { buildBrainGeometry } from './geometry'
import { store, useNox } from '../../lib/store'
import { mapStateToMode, type BrainMode } from '../../lib/types'

interface Params {
  rot: number; jit: number; morph: number; spawn: number
  edgeA: number; coreI: number; boltN: number; boltA: number
}

const TARGET: Record<BrainMode, Params> = {
  idle:  { rot: 0.12, jit: 0.012, morph: 0,    spawn: 1.2, edgeA: 0.10, coreI: 0.45, boltN: 1, boltA: 0.22 },
  think: { rot: 0.55, jit: 0.062, morph: 1,    spawn: 16,  edgeA: 0.26, coreI: 0.95, boltN: 3, boltA: 0.55 },
  speak: { rot: 0.22, jit: 0.024, morph: 0.15, spawn: 7,   edgeA: 0.16, coreI: 0.70, boltN: 2, boltA: 0.45 },
}

const NODE_COUNT = 900
const MAX_PULSES = 160
const MAX_BOLTS = 4
const BOLT_SEGS = 11
const MAX_SPARKS = 24
const WAVE_POOL = 6
const CHIP_Y = -1.42

const lerp = (a: number, b: number, f: number) => a + (b - a) * f

function radialTexture(inner: string, outer: string): THREE.CanvasTexture {
  const cv = document.createElement('canvas')
  cv.width = cv.height = 64
  const ctx = cv.getContext('2d')!
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32)
  g.addColorStop(0, inner)
  g.addColorStop(0.4, outer)
  g.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 64, 64)
  return new THREE.CanvasTexture(cv)
}

function makeBoltPoints(from: THREE.Vector3, to: THREE.Vector3, rng: () => number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = [from.clone()]
  for (let i = 1; i < BOLT_SEGS; i++) {
    const t = i / BOLT_SEGS
    const fall = 1 - Math.abs(2 * t - 1)
    pts.push(new THREE.Vector3(
      lerp(from.x, to.x, t) + (rng() * 2 - 1) * 0.16 * fall,
      lerp(from.y, to.y, t) + (rng() * 2 - 1) * 0.07 * fall,
      lerp(from.z, to.z, t) + (rng() * 2 - 1) * 0.16 * fall,
    ))
  }
  pts.push(to.clone())
  return pts
}

function Chip() {
  const pinGeo = useMemo(() => new THREE.BoxGeometry(0.07, 0.035, 0.2), [])
  const pinMat = useMemo(() => new THREE.MeshBasicMaterial({ color: '#0e7490' }), [])
  const pins = useMemo(() => {
    const list: Array<{ pos: [number, number, number]; rot: number }> = []
    for (let i = -2; i <= 2; i++) {
      const off = i * 0.24
      list.push({ pos: [off, 0, 0.64], rot: 0 })
      list.push({ pos: [off, 0, -0.64], rot: 0 })
      list.push({ pos: [0.64, 0, off], rot: Math.PI / 2 })
      list.push({ pos: [-0.64, 0, off], rot: Math.PI / 2 })
    }
    return list
  }, [])
  const traces = useMemo(() => {
    const verts: number[] = []
    const dirs = [[1, 0], [0, 1], [-1, 0], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]]
    for (const [dx, dz] of dirs) {
      const L = Math.hypot(dx, dz)
      verts.push((dx / L) * 0.8, 0, (dz / L) * 0.8, (dx / L) * 1.9, 0, (dz / L) * 1.9)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
    return geo
  }, [])
  return (
    <group position={[0, CHIP_Y, 0]}>
      <mesh position={[0, -0.03, 0]}>
        <boxGeometry args={[1.16, 0.06, 1.16]} />
        <meshBasicMaterial color="#04141f" />
      </mesh>
      <mesh position={[0, 0.02, 0]}>
        <boxGeometry args={[0.46, 0.05, 0.46]} />
        <meshBasicMaterial color="#0a2c3f" />
      </mesh>
      {pins.map((p, i) => (
        <mesh key={i} position={p.pos} rotation={[0, p.rot, 0]} geometry={pinGeo} material={pinMat} />
      ))}
      <lineSegments geometry={traces} position={[0, -0.05, 0]}>
        <lineBasicMaterial color="#0e7490" transparent opacity={0.35} />
      </lineSegments>
    </group>
  )
}

function BrainScene() {
  const state = useNox(s => s.state)
  const mode = mapStateToMode(state)
  const modeRef = useRef<BrainMode>(mode)
  modeRef.current = mode

  const geo = useMemo(() => buildBrainGeometry(NODE_COUNT, 1337), [])
  const rng = useMemo(() => {
    let a = 99
    return () => {
      a = (a * 1664525 + 1013904223) >>> 0
      return a / 4294967296
    }
  }, [])

  const dotTex = useMemo(() => radialTexture('rgba(190,242,255,1)', 'rgba(56,189,248,0.5)'), [])
  const coreTex = useMemo(() => radialTexture('rgba(255,214,150,1)', 'rgba(255,120,30,0.55)'), [])
  const glowTex = useMemo(() => radialTexture('rgba(34,211,238,0.9)', 'rgba(8,145,178,0.25)'), [])

  const groupRef = useRef<THREE.Group>(null!)
  const pointsRef = useRef<THREE.BufferGeometry>(null!)
  const linesRef = useRef<THREE.BufferGeometry>(null!)
  const lineMatRef = useRef<THREE.LineBasicMaterial>(null!)
  const pulsesRef = useRef<THREE.BufferGeometry>(null!)
  const boltsRef = useRef<THREE.BufferGeometry>(null!)
  const boltMatRef = useRef<THREE.LineBasicMaterial>(null!)
  const sparksRef = useRef<THREE.BufferGeometry>(null!)
  const coreRef = useRef<THREE.Sprite>(null!)
  const chipGlowRef = useRef<THREE.Sprite>(null!)
  const wavesRef = useRef<Array<THREE.Mesh | null>>([])
  const { camera } = useThree()

  // buffers de trabalho
  const work = useMemo(() => ({
    nodePos: new Float32Array(geo.count * 3),
    linePos: new Float32Array(geo.edges.length * 3),
    pulsePos: new Float32Array(MAX_PULSES * 3),
    pulseCol: new Float32Array(MAX_PULSES * 3),
    boltPos: new Float32Array(MAX_BOLTS * BOLT_SEGS * 2 * 3),
    sparkPos: new Float32Array(MAX_SPARKS * 3),
    pulses: [] as Array<{ e: number; t: number; sp: number; hot: boolean }>,
    sparks: [] as Array<{ t: number; sp: number; ox: number; oz: number }>,
    waves: [] as Array<{ mesh: THREE.Mesh; a: number }>,
    P: { ...TARGET.idle } as Params,
    t: 0,
    spawnAcc: 0,
    sparkAcc: 0,
    waveAcc: 0,
    boltTimer: 0,
    env: 0,
    stemTipWorld: new THREE.Vector3(),
  }), [geo])

  useFrame((_, rawDt) => {
    const dt = Math.min(0.05, rawDt)
    const w = work
    w.t += dt
    const m = modeRef.current
    const tg = TARGET[m]
    const f = 1 - Math.pow(0.0018, dt)
    const P = w.P
    P.rot = lerp(P.rot, tg.rot, f); P.jit = lerp(P.jit, tg.jit, f)
    P.morph = lerp(P.morph, tg.morph, f); P.spawn = lerp(P.spawn, tg.spawn, f)
    P.edgeA = lerp(P.edgeA, tg.edgeA, f); P.coreI = lerp(P.coreI, tg.coreI, f)
    P.boltN = lerp(P.boltN, tg.boltN, f); P.boltA = lerp(P.boltA, tg.boltA, f)

    // nível de voz real (suavizado); fallback sintético se não houver eventos viz
    const rawLevel = store.getState().level
    let envTarget = 0
    if (m === 'speak') {
      envTarget = rawLevel > 0.01
        ? Math.min(1, rawLevel)
        : Math.min(1, Math.max(0, Math.sin(w.t * 7.3) + 0.55 * Math.sin(w.t * 19.1 + 1.3) + 0.35 * Math.sin(w.t * 3.7 + 0.5)) * 0.62)
    } else if (m === 'idle') {
      envTarget = Math.min(0.45, rawLevel) // reação sutil à voz do usuário
    }
    w.env = lerp(w.env, envTarget, Math.min(1, dt * 14))
    const env = w.env

    const breath = 1 + 0.016 * Math.sin(w.t * 0.9)
    const morphWave = P.morph * (0.5 + 0.5 * Math.sin(w.t * 1.6))

    const g = groupRef.current
    g.rotation.y += P.rot * dt
    g.rotation.x = 0.14
    const s = breath * (1 + 0.05 * env)
    g.scale.setScalar(s)

    // posições dos nós (morph + jitter)
    const np = w.nodePos
    for (let i = 0; i < geo.count; i++) {
      const i3 = i * 3
      const stem = geo.isStem[i] === 1
      const jm = (stem ? 0.25 : 1) * P.jit
      const ph = geo.phases[i]
      const sp = geo.speeds[i]
      const mw = stem ? 0 : morphWave
      np[i3] = lerp(geo.positions[i3], geo.altPositions[i3], mw) +
        jm * Math.sin(w.t * sp * 2.1 + ph) * geo.jitterDirs[i3]
      np[i3 + 1] = lerp(geo.positions[i3 + 1], geo.altPositions[i3 + 1], mw) +
        jm * Math.sin(w.t * sp * 1.7 + ph * 1.4) * geo.jitterDirs[i3 + 1]
      np[i3 + 2] = lerp(geo.positions[i3 + 2], geo.altPositions[i3 + 2], mw) +
        jm * Math.sin(w.t * sp * 2.5 + ph * 0.7) * geo.jitterDirs[i3 + 2]
    }
    pointsRef.current.attributes.position.array.set(np)
    pointsRef.current.attributes.position.needsUpdate = true

    // arestas
    const lp = w.linePos
    for (let e = 0; e < geo.edges.length; e++) {
      const n3 = geo.edges[e] * 3
      const e3 = e * 3
      lp[e3] = np[n3]; lp[e3 + 1] = np[n3 + 1]; lp[e3 + 2] = np[n3 + 2]
    }
    linesRef.current.attributes.position.array.set(lp)
    linesRef.current.attributes.position.needsUpdate = true
    lineMatRef.current.opacity = P.edgeA * (m === 'speak' ? 0.55 + 0.85 * env : 1) * 2.2

    // pulsos sinápticos
    w.spawnAcc += dt * P.spawn
    while (w.spawnAcc > 1 && w.pulses.length < MAX_PULSES) {
      w.spawnAcc -= 1
      w.pulses.push({ e: (rng() * (geo.edges.length / 2)) | 0, t: 0, sp: 1.2 + rng() * 1.4, hot: rng() < 0.3 })
    }
    const pp = w.pulsePos
    const pc = w.pulseCol
    pp.fill(9999)
    let pi = 0
    w.pulses = w.pulses.filter(p => {
      p.t += dt * p.sp
      if (p.t >= 1 || pi >= MAX_PULSES) return false
      const a3 = geo.edges[p.e * 2] * 3
      const b3 = geo.edges[p.e * 2 + 1] * 3
      const k3 = pi * 3
      pp[k3] = lerp(np[a3], np[b3], p.t)
      pp[k3 + 1] = lerp(np[a3 + 1], np[b3 + 1], p.t)
      pp[k3 + 2] = lerp(np[a3 + 2], np[b3 + 2], p.t)
      if (p.hot) { pc[k3] = 1; pc[k3 + 1] = 0.62; pc[k3 + 2] = 0.32 }
      else { pc[k3] = 0.7; pc[k3 + 1] = 0.95; pc[k3 + 2] = 1 }
      pi++
      return true
    })
    pulsesRef.current.attributes.position.array.set(pp)
    pulsesRef.current.attributes.position.needsUpdate = true
    pulsesRef.current.attributes.color.array.set(pc)
    pulsesRef.current.attributes.color.needsUpdate = true

    // núcleo
    const flick = m === 'think' ? 0.85 + 0.15 * Math.sin(w.t * 23) + 0.08 * Math.sin(w.t * 41) : 1
    const coreS = (0.55 + 0.35 * env) * flick
    coreRef.current.scale.setScalar(coreS)
    ;(coreRef.current.material as THREE.SpriteMaterial).opacity = P.coreI * (0.75 + 0.25 * env)

    // ponta do tronco em coordenadas de mundo (o grupo gira; o chip não)
    const tip3 = geo.stemTipIndex * 3
    w.stemTipWorld.set(np[tip3], np[tip3 + 1], np[tip3 + 2])
    g.localToWorld(w.stemTipWorld)

    // raios tronco→chip
    w.boltTimer -= dt
    if (w.boltTimer <= 0) {
      w.boltTimer = 0.05 + rng() * 0.06
      const bp = w.boltPos
      bp.fill(9999)
      const nb = Math.min(MAX_BOLTS, Math.round(P.boltN + (m === 'speak' ? env * 1.5 : 0)))
      const chipTarget = new THREE.Vector3(0, CHIP_Y + 0.06, 0)
      for (let b = 0; b < nb; b++) {
        const from = w.stemTipWorld.clone()
        from.x += (rng() * 2 - 1) * 0.05
        from.z += (rng() * 2 - 1) * 0.05
        const to = chipTarget.clone()
        to.x += (rng() * 2 - 1) * 0.12
        to.z += (rng() * 2 - 1) * 0.12
        const pts = makeBoltPoints(from, to, rng)
        for (let i = 0; i < BOLT_SEGS; i++) {
          const base = (b * BOLT_SEGS + i) * 6
          bp[base] = pts[i].x; bp[base + 1] = pts[i].y; bp[base + 2] = pts[i].z
          bp[base + 3] = pts[i + 1].x; bp[base + 4] = pts[i + 1].y; bp[base + 5] = pts[i + 1].z
        }
      }
      boltsRef.current.attributes.position.array.set(bp)
      boltsRef.current.attributes.position.needsUpdate = true
    }
    boltMatRef.current.opacity = P.boltA * (m === 'speak' ? 0.4 + 0.8 * env : 1)

    // partículas de energia chip→tronco
    w.sparkAcc += dt * (m === 'think' ? 10 : m === 'speak' ? 3 + 7 * env : 2)
    while (w.sparkAcc > 1 && w.sparks.length < MAX_SPARKS) {
      w.sparkAcc -= 1
      w.sparks.push({ t: 0, sp: 0.5 + rng() * 0.4, ox: (rng() * 2 - 1) * 0.18, oz: (rng() * 2 - 1) * 0.18 })
    }
    const kp = w.sparkPos
    kp.fill(9999)
    let ki = 0
    w.sparks = w.sparks.filter(sk => {
      sk.t += dt * sk.sp
      if (sk.t >= 1 || ki >= MAX_SPARKS) return false
      const k3 = ki * 3
      kp[k3] = lerp(sk.ox, w.stemTipWorld.x, sk.t)
      kp[k3 + 1] = lerp(CHIP_Y + 0.08, w.stemTipWorld.y, sk.t) + 0.25 * Math.sin(Math.PI * sk.t)
      kp[k3 + 2] = lerp(sk.oz, w.stemTipWorld.z, sk.t)
      ki++
      return true
    })
    sparksRef.current.attributes.position.array.set(kp)
    sparksRef.current.attributes.position.needsUpdate = true

    // brilho de contato do chip
    const chipGlow = m === 'think'
      ? 0.6 + 0.4 * Math.abs(Math.sin(w.t * 9))
      : m === 'speak' ? 0.3 + 0.7 * env : 0.25 + 0.1 * Math.sin(w.t * 1.2)
    ;(chipGlowRef.current.material as THREE.SpriteMaterial).opacity = 0.35 + 0.55 * chipGlow
    chipGlowRef.current.scale.setScalar(0.5 + 0.25 * chipGlow)

    // ondas de voz (anéis billboard)
    w.waveAcc += dt
    if (m === 'speak' && env > 0.55 && w.waveAcc > 0.22) {
      w.waveAcc = 0
      const free = wavesRef.current.find(mh => mh && !mh.visible)
      if (free) {
        free.visible = true
        free.scale.setScalar(0.3)
        w.waves.push({ mesh: free, a: 0.5 })
      }
    }
    w.waves = w.waves.filter(wv => {
      wv.a -= dt * 0.55
      const sc = wv.mesh.scale.x + dt * 1.6
      wv.mesh.scale.setScalar(sc)
      wv.mesh.quaternion.copy(camera.quaternion)
      ;(wv.mesh.material as THREE.MeshBasicMaterial).opacity = Math.max(0, wv.a)
      if (wv.a <= 0) {
        wv.mesh.visible = false
        return false
      }
      return true
    })
  })

  return (
    <>
      <group ref={groupRef} position={[0, 0.3, 0]}>
        <points>
          <bufferGeometry ref={pointsRef}>
            <bufferAttribute attach="attributes-position" args={[new Float32Array(geo.positions), 3]} />
          </bufferGeometry>
          <pointsMaterial map={dotTex} color="#7dd3fc" size={0.05} sizeAttenuation transparent
            opacity={0.9} depthWrite={false} blending={THREE.AdditiveBlending} />
        </points>
        <lineSegments>
          <bufferGeometry ref={linesRef}>
            <bufferAttribute attach="attributes-position" args={[new Float32Array(geo.edges.length * 3), 3]} />
          </bufferGeometry>
          <lineBasicMaterial ref={lineMatRef} color="#38bdf8" transparent opacity={0.2}
            depthWrite={false} blending={THREE.AdditiveBlending} />
        </lineSegments>
        <points>
          <bufferGeometry ref={pulsesRef}>
            <bufferAttribute attach="attributes-position" args={[new Float32Array(MAX_PULSES * 3).fill(9999), 3]} />
            <bufferAttribute attach="attributes-color" args={[new Float32Array(MAX_PULSES * 3), 3]} />
          </bufferGeometry>
          <pointsMaterial map={glowTex} vertexColors size={0.11} sizeAttenuation transparent
            opacity={0.95} depthWrite={false} blending={THREE.AdditiveBlending} />
        </points>
        <sprite ref={coreRef} position={[0, 0, 0]} scale={0.55}>
          <spriteMaterial map={coreTex} transparent opacity={0.45} depthWrite={false}
            blending={THREE.AdditiveBlending} />
        </sprite>
        {Array.from({ length: WAVE_POOL }).map((_, i) => (
          <mesh key={i} visible={false} ref={el => { wavesRef.current[i] = el }}>
            <ringGeometry args={[0.94, 1, 48]} />
            <meshBasicMaterial color="#ff8c42" transparent opacity={0} side={THREE.DoubleSide}
              depthWrite={false} blending={THREE.AdditiveBlending} />
          </mesh>
        ))}
      </group>

      <Chip />
      <sprite ref={chipGlowRef} position={[0, CHIP_Y + 0.1, 0]} scale={0.55}>
        <spriteMaterial map={coreTex} transparent opacity={0.4} depthWrite={false}
          blending={THREE.AdditiveBlending} />
      </sprite>
      <lineSegments>
        <bufferGeometry ref={boltsRef}>
          <bufferAttribute attach="attributes-position" args={[new Float32Array(MAX_BOLTS * BOLT_SEGS * 2 * 3).fill(9999), 3]} />
        </bufferGeometry>
        <lineBasicMaterial ref={boltMatRef} color="#d6fbff" transparent opacity={0.3}
          depthWrite={false} blending={THREE.AdditiveBlending} />
      </lineSegments>
      <points>
        <bufferGeometry ref={sparksRef}>
          <bufferAttribute attach="attributes-position" args={[new Float32Array(MAX_SPARKS * 3).fill(9999), 3]} />
        </bufferGeometry>
        <pointsMaterial map={glowTex} color="#7dd3fc" size={0.07} sizeAttenuation transparent
          opacity={0.8} depthWrite={false} blending={THREE.AdditiveBlending} />
      </points>

      <EffectComposer>
        <Bloom intensity={0.85} luminanceThreshold={0.16} luminanceSmoothing={0.25} mipmapBlur radius={0.62} />
      </EffectComposer>
    </>
  )
}

export default function Brain3D() {
  return (
    <Canvas
      dpr={[1, 2]}
      gl={{ alpha: true, antialias: true, powerPreference: 'high-performance' }}
      camera={{ position: [0, 0.35, 4.4], fov: 42 }}
      style={{ background: 'transparent' }}
    >
      <BrainScene />
    </Canvas>
  )
}
