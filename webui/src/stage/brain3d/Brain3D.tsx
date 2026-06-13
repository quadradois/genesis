// Cérebro neural 3D do Nox — React Three Fiber + bloom.
// Estados: idle (respiração) / think (morph + cascata) / speak (pulso pela voz real).
// O visual holográfico vem de: arestas curtas no córtex, cor por vértice com
// atenuação de profundidade (frente clara, fundo escuro), halo atmosférico e
// bloom intenso. Nível de voz lido imperativamente no frame loop (sem re-render).
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

const NODE_COUNT = 1800
const MAX_PULSES = 220
const MAX_BOLTS = 4
const BOLT_SEGS = 11
const MAX_SPARKS = 24
const WAVE_POOL = 6
const CHIP_Y = -1.5
const BRAIN_Y = 0.42

// gradiente de profundidade (frente → fundo)
const FRONT = { r: 0.82, g: 0.96, b: 1.0 }
const BACK = { r: 0.07, g: 0.27, b: 0.4 }

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

function dynGeo(count: number, withColor: boolean): THREE.BufferGeometry {
  const geo = new THREE.BufferGeometry()
  const pos = new THREE.Float32BufferAttribute(new Float32Array(count * 3).fill(9999), 3)
  pos.setUsage(THREE.DynamicDrawUsage)
  geo.setAttribute('position', pos)
  if (withColor) {
    const col = new THREE.Float32BufferAttribute(new Float32Array(count * 3), 3)
    col.setUsage(THREE.DynamicDrawUsage)
    geo.setAttribute('color', col)
  }
  return geo
}

function makeBoltInto(out: Float32Array, base: number, from: THREE.Vector3, to: THREE.Vector3, rng: () => number) {
  let px = from.x, py = from.y, pz = from.z
  for (let i = 1; i <= BOLT_SEGS; i++) {
    const t = i / BOLT_SEGS
    const fall = 1 - Math.abs(2 * t - 1)
    const nx = t < 1 ? lerp(from.x, to.x, t) + (rng() * 2 - 1) * 0.14 * fall : to.x
    const ny = t < 1 ? lerp(from.y, to.y, t) + (rng() * 2 - 1) * 0.06 * fall : to.y
    const nz = t < 1 ? lerp(from.z, to.z, t) + (rng() * 2 - 1) * 0.14 * fall : to.z
    const o = base + (i - 1) * 6
    out[o] = px; out[o + 1] = py; out[o + 2] = pz
    out[o + 3] = nx; out[o + 4] = ny; out[o + 5] = nz
    px = nx; py = ny; pz = nz
  }
}

// Chip holográfico: esquemático de linhas finas (guia FUI da skill ui-ux-pro-max:
// "thin lines, technical markers, decorative brackets"), nada de volumes sólidos.
function Chip({ glowTex }: { glowTex: THREE.Texture }) {
  const squareGeo = (s: number) => {
    const g2 = new THREE.BufferGeometry()
    g2.setAttribute('position', new THREE.Float32BufferAttribute(
      [-s, 0, -s, s, 0, -s, s, 0, s, -s, 0, s], 3,
    ))
    return g2
  }
  const rings = useMemo(() => [squareGeo(0.52), squareGeo(0.34), squareGeo(0.13)], [])
  const brackets = useMemo(() => {
    // cantoneiras HUD nos 4 cantos
    const v: number[] = []
    const L = 0.16
    const S = 0.68
    for (const [cx, cz] of [[-S, -S], [S, -S], [S, S], [-S, S]] as const) {
      const sx = Math.sign(cx)
      const sz = Math.sign(cz)
      v.push(cx, 0, cz - sz * L, cx, 0, cz, cx, 0, cz, cx - sx * L, 0, cz)
    }
    const g2 = new THREE.BufferGeometry()
    g2.setAttribute('position', new THREE.Float32BufferAttribute(v, 3))
    return g2
  }, [])
  const pads = useMemo(() => {
    // pads delicados ao longo das bordas (pontos, não "dentes")
    const v: number[] = []
    for (let i = -3; i <= 3; i++) {
      const o = i * 0.13
      v.push(o, 0, 0.52, o, 0, -0.52, 0.52, 0, o, -0.52, 0, o)
    }
    const g2 = new THREE.BufferGeometry()
    g2.setAttribute('position', new THREE.Float32BufferAttribute(v, 3))
    return g2
  }, [])
  const traces = useMemo(() => {
    const verts: number[] = []
    const dot: number[] = []
    const dirs = [[1, 0], [0, 1], [-1, 0], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]]
    for (const [dx, dz] of dirs) {
      const L = Math.hypot(dx, dz)
      const ux = dx / L
      const uz = dz / L
      const mx = ux * 1.2, mz = uz * 1.2
      const ex = ux * 1.85 + uz * 0.16, ez = uz * 1.85 - ux * 0.16
      verts.push(ux * 0.7, 0, uz * 0.7, mx, 0, mz, mx, 0, mz, ex, 0, ez)
      dot.push(ex, 0.001, ez)
    }
    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3))
    const dotGeo = new THREE.BufferGeometry()
    dotGeo.setAttribute('position', new THREE.Float32BufferAttribute(dot, 3))
    return { lineGeo, dotGeo }
  }, [])
  return (
    <group position={[0, CHIP_Y, 0]} rotation={[0, 0.6, 0]}>
      <sprite position={[0, -0.02, 0]} scale={2.8}>
        <spriteMaterial map={glowTex} transparent opacity={0.09} depthWrite={false}
          blending={THREE.AdditiveBlending} color="#0891b2" />
      </sprite>
      {/* placa: plano fino e escuro, quase invisível — só ancora as linhas */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.006, 0]}>
        <planeGeometry args={[1.34, 1.34]} />
        <meshBasicMaterial color="#02101a" transparent opacity={0.8} />
      </mesh>
      <lineLoop geometry={rings[0]}>
        <lineBasicMaterial color="#22d3ee" transparent opacity={0.5} />
      </lineLoop>
      <lineLoop geometry={rings[1]}>
        <lineBasicMaterial color="#0e7490" transparent opacity={0.4} />
      </lineLoop>
      <lineLoop geometry={rings[2]} position={[0, 0.004, 0]}>
        <lineBasicMaterial color="#67e8f9" transparent opacity={0.75} />
      </lineLoop>
      <lineSegments geometry={brackets}>
        <lineBasicMaterial color="#22d3ee" transparent opacity={0.8} />
      </lineSegments>
      <points geometry={pads}>
        <pointsMaterial map={glowTex} color="#155e75" size={0.04} sizeAttenuation transparent
          opacity={0.6} depthWrite={false} blending={THREE.AdditiveBlending} />
      </points>
      <lineSegments geometry={traces.lineGeo} position={[0, -0.004, 0]}>
        <lineBasicMaterial color="#0e7490" transparent opacity={0.3} />
      </lineSegments>
      <points geometry={traces.dotGeo} position={[0, -0.004, 0]}>
        <pointsMaterial map={glowTex} color="#22d3ee" size={0.05} sizeAttenuation transparent
          opacity={0.6} depthWrite={false} blending={THREE.AdditiveBlending} />
      </points>
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

  const dotTex = useMemo(() => radialTexture('rgba(220,248,255,1)', 'rgba(56,189,248,0.45)'), [])
  const coreTex = useMemo(() => radialTexture('rgba(255,214,150,1)', 'rgba(255,120,30,0.55)'), [])
  const glowTex = useMemo(() => radialTexture('rgba(34,211,238,0.9)', 'rgba(8,145,178,0.25)'), [])

  const geos = useMemo(() => ({
    nodes: dynGeo(geo.count, true),
    lines: dynGeo(geo.edges.length, true),
    pulses: dynGeo(MAX_PULSES, true),
    bolts: dynGeo(MAX_BOLTS * BOLT_SEGS * 2, false),
    sparks: dynGeo(MAX_SPARKS, false),
  }), [geo])

  const groupRef = useRef<THREE.Group>(null!)
  const lineMatRef = useRef<THREE.LineBasicMaterial>(null!)
  const boltMatRef = useRef<THREE.LineBasicMaterial>(null!)
  const coreRef = useRef<THREE.Sprite>(null!)
  const chipGlowRef = useRef<THREE.Sprite>(null!)
  const wavesRef = useRef<Array<THREE.Mesh | null>>([])
  const { camera } = useThree()

  const work = useMemo(() => ({
    nodePos: new Float32Array(geo.count * 3),
    pulses: [] as Array<{ e: number; t: number; sp: number; hot: boolean }>,
    sparks: [] as Array<{ t: number; sp: number; ox: number; oz: number }>,
    waves: [] as Array<{ mesh: THREE.Mesh; a: number }>,
    P: { ...TARGET.idle } as Params,
    t: 0, spawnAcc: 0, sparkAcc: 0, waveAcc: 0, boltTimer: 0, env: 0,
    stemTipWorld: new THREE.Vector3(),
    chipTarget: new THREE.Vector3(),
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

    const rawLevel = store.getState().level
    let envTarget = 0
    if (m === 'speak') {
      envTarget = rawLevel > 0.01
        ? Math.min(1, rawLevel)
        : Math.min(1, Math.max(0, Math.sin(w.t * 7.3) + 0.55 * Math.sin(w.t * 19.1 + 1.3) + 0.35 * Math.sin(w.t * 3.7 + 0.5)) * 0.62)
    } else if (m === 'idle') {
      envTarget = Math.min(0.45, rawLevel)
    }
    w.env = lerp(w.env, envTarget, Math.min(1, dt * 14))
    const env = w.env

    const breath = 1 + 0.016 * Math.sin(w.t * 0.9)
    const morphWave = P.morph * (0.5 + 0.5 * Math.sin(w.t * 1.6))

    const g = groupRef.current
    g.rotation.y += P.rot * dt
    g.rotation.x = 0.14
    const s = breath * (1 + 0.05 * env)
    g.scale.set(s * 1.06, s, s) // leve alongamento anatômico

    // profundidade analítica (o grupo gira em Y; frente = +z rotacionado)
    const ang = g.rotation.y
    const ca = Math.cos(ang)
    const sa = Math.sin(ang)

    const np = w.nodePos
    const nodeCol = geos.nodes.attributes.color.array as Float32Array
    for (let i = 0; i < geo.count; i++) {
      const i3 = i * 3
      const stem = geo.isStem[i] === 1
      const jm = (stem ? 0.25 : 1) * P.jit
      const ph = geo.phases[i]
      const sp = geo.speeds[i]
      const mw = stem ? 0 : morphWave
      const x = lerp(geo.positions[i3], geo.altPositions[i3], mw) +
        jm * Math.sin(w.t * sp * 2.1 + ph) * geo.jitterDirs[i3]
      const y = lerp(geo.positions[i3 + 1], geo.altPositions[i3 + 1], mw) +
        jm * Math.sin(w.t * sp * 1.7 + ph * 1.4) * geo.jitterDirs[i3 + 1]
      const z = lerp(geo.positions[i3 + 2], geo.altPositions[i3 + 2], mw) +
        jm * Math.sin(w.t * sp * 2.5 + ph * 0.7) * geo.jitterDirs[i3 + 2]
      np[i3] = x; np[i3 + 1] = y; np[i3 + 2] = z
      // z no espaço da câmera (após rotação Y do grupo)
      const rz = -x * sa + z * ca
      let depth = (rz + 1.3) / 2.6
      depth = depth < 0 ? 0 : depth > 1 ? 1 : depth
      const dim = stem ? 0.85 : 1
      nodeCol[i3] = lerp(BACK.r, FRONT.r, depth) * dim
      nodeCol[i3 + 1] = lerp(BACK.g, FRONT.g, depth) * dim
      nodeCol[i3 + 2] = lerp(BACK.b, FRONT.b, depth) * dim
    }
    ;(geos.nodes.attributes.position.array as Float32Array).set(np)
    geos.nodes.attributes.position.needsUpdate = true
    geos.nodes.attributes.color.needsUpdate = true

    const lp = geos.lines.attributes.position.array as Float32Array
    const lc = geos.lines.attributes.color.array as Float32Array
    for (let e = 0; e < geo.edges.length; e++) {
      const n = geo.edges[e]
      const n3 = n * 3
      const e3 = e * 3
      lp[e3] = np[n3]; lp[e3 + 1] = np[n3 + 1]; lp[e3 + 2] = np[n3 + 2]
      lc[e3] = nodeCol[n3] * 0.8; lc[e3 + 1] = nodeCol[n3 + 1] * 0.8; lc[e3 + 2] = nodeCol[n3 + 2] * 0.8
    }
    geos.lines.attributes.position.needsUpdate = true
    geos.lines.attributes.color.needsUpdate = true
    lineMatRef.current.opacity = P.edgeA * (m === 'speak' ? 0.55 + 0.85 * env : 1) * 1.15

    // pulsos sinápticos
    w.spawnAcc += dt * P.spawn
    while (w.spawnAcc > 1 && w.pulses.length < MAX_PULSES) {
      w.spawnAcc -= 1
      w.pulses.push({ e: (rng() * (geo.edges.length / 2)) | 0, t: 0, sp: 1.2 + rng() * 1.4, hot: rng() < 0.3 })
    }
    const pp = geos.pulses.attributes.position.array as Float32Array
    const pc = geos.pulses.attributes.color.array as Float32Array
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
      if (p.hot) { pc[k3] = 1; pc[k3 + 1] = 0.62; pc[k3 + 2] = 0.3 }
      else { pc[k3] = 0.75; pc[k3 + 1] = 0.97; pc[k3 + 2] = 1 }
      pi++
      return true
    })
    geos.pulses.attributes.position.needsUpdate = true
    geos.pulses.attributes.color.needsUpdate = true

    // núcleo
    const flick = m === 'think' ? 0.85 + 0.15 * Math.sin(w.t * 23) + 0.08 * Math.sin(w.t * 41) : 1
    coreRef.current.scale.setScalar((0.5 + 0.32 * env) * flick)
    ;(coreRef.current.material as THREE.SpriteMaterial).opacity = P.coreI * (0.7 + 0.3 * env)

    // ponta do tronco no mundo
    const tip3 = geo.stemTipIndex * 3
    w.stemTipWorld.set(np[tip3], np[tip3 + 1], np[tip3 + 2])
    g.localToWorld(w.stemTipWorld)

    // raios tronco→chip
    w.boltTimer -= dt
    if (w.boltTimer <= 0) {
      w.boltTimer = 0.05 + rng() * 0.06
      const bp = geos.bolts.attributes.position.array as Float32Array
      bp.fill(9999)
      const nb = Math.min(MAX_BOLTS, Math.round(P.boltN + (m === 'speak' ? env * 1.5 : 0)))
      for (let b = 0; b < nb; b++) {
        const from = w.stemTipWorld
        w.chipTarget.set((rng() * 2 - 1) * 0.1, CHIP_Y + 0.05, (rng() * 2 - 1) * 0.1)
        const fromJ = new THREE.Vector3(
          from.x + (rng() * 2 - 1) * 0.04, from.y, from.z + (rng() * 2 - 1) * 0.04,
        )
        makeBoltInto(bp, b * BOLT_SEGS * 6, fromJ, w.chipTarget, rng)
      }
      geos.bolts.attributes.position.needsUpdate = true
    }
    boltMatRef.current.opacity = P.boltA * (m === 'speak' ? 0.4 + 0.8 * env : 1)

    // partículas de energia chip→tronco
    w.sparkAcc += dt * (m === 'think' ? 10 : m === 'speak' ? 3 + 7 * env : 2)
    while (w.sparkAcc > 1 && w.sparks.length < MAX_SPARKS) {
      w.sparkAcc -= 1
      w.sparks.push({ t: 0, sp: 0.5 + rng() * 0.4, ox: (rng() * 2 - 1) * 0.16, oz: (rng() * 2 - 1) * 0.16 })
    }
    const kp = geos.sparks.attributes.position.array as Float32Array
    kp.fill(9999)
    let ki = 0
    w.sparks = w.sparks.filter(sk => {
      sk.t += dt * sk.sp
      if (sk.t >= 1 || ki >= MAX_SPARKS) return false
      const k3 = ki * 3
      kp[k3] = lerp(sk.ox, w.stemTipWorld.x, sk.t)
      kp[k3 + 1] = lerp(CHIP_Y + 0.07, w.stemTipWorld.y, sk.t) + 0.22 * Math.sin(Math.PI * sk.t)
      kp[k3 + 2] = lerp(sk.oz, w.stemTipWorld.z, sk.t)
      ki++
      return true
    })
    geos.sparks.attributes.position.needsUpdate = true

    // brilho de contato do chip
    const chipGlow = m === 'think'
      ? 0.6 + 0.4 * Math.abs(Math.sin(w.t * 9))
      : m === 'speak' ? 0.3 + 0.7 * env : 0.25 + 0.1 * Math.sin(w.t * 1.2)
    ;(chipGlowRef.current.material as THREE.SpriteMaterial).opacity = 0.22 + 0.4 * chipGlow
    chipGlowRef.current.scale.setScalar(0.3 + 0.16 * chipGlow)

    // ondas de voz
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
      wv.mesh.scale.setScalar(wv.mesh.scale.x + dt * 1.6)
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
      <group ref={groupRef} position={[0, BRAIN_Y, 0]}>
        <points geometry={geos.nodes}>
          <pointsMaterial map={dotTex} vertexColors size={0.075} sizeAttenuation transparent
            opacity={0.95} depthWrite={false} blending={THREE.AdditiveBlending} />
        </points>
        <lineSegments geometry={geos.lines}>
          <lineBasicMaterial ref={lineMatRef} vertexColors transparent opacity={0.14}
            depthWrite={false} blending={THREE.AdditiveBlending} />
        </lineSegments>
        <points geometry={geos.pulses}>
          <pointsMaterial map={glowTex} vertexColors size={0.12} sizeAttenuation transparent
            opacity={0.95} depthWrite={false} blending={THREE.AdditiveBlending} />
        </points>
        <sprite ref={coreRef} position={[0, 0, 0]} scale={0.5}>
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

      <Chip glowTex={glowTex} />
      <sprite ref={chipGlowRef} position={[0, CHIP_Y + 0.09, 0]} scale={0.5}>
        <spriteMaterial map={coreTex} transparent opacity={0.4} depthWrite={false}
          blending={THREE.AdditiveBlending} />
      </sprite>
      <lineSegments geometry={geos.bolts}>
        <lineBasicMaterial ref={boltMatRef} color="#eaffff" transparent opacity={0.3}
          depthWrite={false} blending={THREE.AdditiveBlending} />
      </lineSegments>
      <points geometry={geos.sparks}>
        <pointsMaterial map={glowTex} color="#7dd3fc" size={0.06} sizeAttenuation transparent
          opacity={0.8} depthWrite={false} blending={THREE.AdditiveBlending} />
      </points>

      <EffectComposer>
        <Bloom intensity={1.1} luminanceThreshold={0.12} luminanceSmoothing={0.2} mipmapBlur radius={0.48} />
      </EffectComposer>
    </>
  )
}

export default function Brain3D() {
  return (
    <Canvas
      dpr={[1, 2]}
      gl={{ alpha: true, antialias: true, powerPreference: 'high-performance' }}
      camera={{ position: [0, 0.3, 4.6], fov: 42 }}
      style={{ background: 'transparent' }}
    >
      <BrainScene />
    </Canvas>
  )
}
