import type { BrainMode } from '../lib/types'

interface Node3 {
  bx: number; by: number; bz: number
  ax: number; ay: number; az: number
  ph: number; sp: number
  dx: number; dy: number; dz: number
  stem: boolean
  sx: number; sy: number; depth: number
}

interface Params { rot: number; jit: number; morph: number; spawn: number; edgeA: number; coreI: number; boltN: number; boltA: number }

const TARGET: Record<BrainMode, Params> = {
  idle:  { rot: 0.12, jit: 0.012, morph: 0,    spawn: 1.2, edgeA: 0.10, coreI: 0.45, boltN: 1, boltA: 0.22 },
  think: { rot: 0.55, jit: 0.062, morph: 1,    spawn: 16,  edgeA: 0.26, coreI: 0.95, boltN: 3, boltA: 0.55 },
  speak: { rot: 0.22, jit: 0.024, morph: 0.15, spawn: 7,   edgeA: 0.16, coreI: 0.70, boltN: 2, boltA: 0.45 },
}

const rnd = (a: number, b: number) => a + Math.random() * (b - a)
const lerp = (a: number, b: number, f: number) => a + (b - a) * f

function insideBrain(x: number, y: number, z: number): boolean {
  let inCer = ((x - 0.06) ** 2) / 1.21 + ((y - 0.16) ** 2) / 0.4356 + (z * z) / 0.5476 <= 1
  if (inCer && y < -0.34) inCer = false
  const inT1 = ((x - 0.18) ** 2) / 0.2704 + ((y + 0.22) ** 2) / 0.0729 + ((z - 0.46) ** 2) / 0.0729 <= 1
  const inT2 = ((x - 0.18) ** 2) / 0.2704 + ((y + 0.22) ** 2) / 0.0729 + ((z + 0.46) ** 2) / 0.0729 <= 1
  const inCb = ((x + 0.74) ** 2) / 0.1156 + ((y + 0.40) ** 2) / 0.0576 + (z * z) / 0.16 <= 1
  return inCer || inT1 || inT2 || inCb
}
const inFissure = (_x: number, y: number, z: number) => Math.abs(z) < 0.055 && y > 0.28

export interface BrainHandle { setMode(m: BrainMode): void; setLevel(l: number): void; destroy(): void }

export function createBrain(cv: HTMLCanvasElement): BrainHandle {
  const ctx = cv.getContext('2d')!
  const DPR = Math.min(window.devicePixelRatio || 1, 2)
  let W = 0, H = 0
  let mode: BrainMode = 'idle'
  let extLevel = 0  // nível de voz vindo do backend (M2); M1: 0 = usa envelope sintético

  const C = { x: 0, y: -0.04, z: 0 }
  function radiusInDir(dx: number, dy: number, dz: number): number {
    let lo = 0, hi = 2.2
    for (let i = 0; i < 16; i++) {
      const m = (lo + hi) / 2
      if (insideBrain(C.x + dx * m, C.y + dy * m, C.z + dz * m)) lo = m; else hi = m
    }
    return lo
  }
  const gyri = (x: number, y: number, z: number) =>
    1 + 0.05 * Math.sin(6 * Math.atan2(z, x) + 2.2 * y) * Math.cos(5.1 * y + 1.3)

  // ---- nós ----
  const N = 235
  const nodes: Node3[] = []
  let tries = 0
  while (nodes.length < N && tries < 60000) {
    tries++
    let x: number, y: number, z: number
    if (Math.random() < 0.64) {
      let dx = rnd(-1, 1), dy = rnd(-1, 1), dz = rnd(-1, 1)
      const L = Math.hypot(dx, dy, dz); if (L < 0.001) continue
      dx /= L; dy /= L; dz /= L
      const R = radiusInDir(dx, dy, dz); if (R < 0.15) continue
      const rr = R * rnd(0.88, 1.0)
      x = C.x + dx * rr; y = C.y + dy * rr; z = C.z + dz * rr
      const g = gyri(x, y, z); x *= g; y *= g; z *= g
    } else {
      x = rnd(-1.25, 1.25); y = rnd(-0.85, 0.95); z = rnd(-0.85, 0.85)
      if (!insideBrain(x, y, z)) continue
    }
    if (inFissure(x, y, z)) continue
    nodes.push({
      bx: x, by: y, bz: z,
      ax: x * 1.15 + 0.09 * Math.sin(7 * y), ay: y * 1.09 + 0.07 * Math.sin(6 * x), az: z * 1.2,
      ph: Math.random() * Math.PI * 2, sp: rnd(0.5, 1.4),
      dx: rnd(-1, 1), dy: rnd(-1, 1), dz: rnd(-1, 1),
      stem: false, sx: 0, sy: 0, depth: 0,
    })
  }
  const stemIdx: number[] = []
  for (let s = 0; s < 7; s++) {
    const tt = s / 6
    const sx = lerp(-0.18, -0.02, tt) + 0.04 * Math.sin(tt * 3)
    const sy = lerp(-0.34, -1.05, tt)
    nodes.push({ bx: sx, by: sy, bz: 0, ax: sx, ay: sy, az: 0, ph: Math.random() * 6.28, sp: 0.6, dx: 0.2, dy: 0.1, dz: 0.2, stem: true, sx: 0, sy: 0, depth: 0.8 })
    stemIdx.push(nodes.length - 1)
  }

  // ---- arestas ----
  const edges: Array<[number, number]> = []
  const seen = new Set<string>()
  const addEdge = (a: number, b: number) => {
    const k = `${Math.min(a, b)}-${Math.max(a, b)}`
    if (!seen.has(k)) { seen.add(k); edges.push([a, b]) }
  }
  for (let i = 0; i < nodes.length; i++) {
    if (nodes[i].stem) continue
    const d: Array<[number, number]> = []
    for (let j = 0; j < nodes.length; j++) {
      if (i === j || nodes[j].stem) continue
      const dx = nodes[i].bx - nodes[j].bx, dy = nodes[i].by - nodes[j].by, dz = nodes[i].bz - nodes[j].bz
      d.push([dx * dx + dy * dy + dz * dz, j])
    }
    d.sort((a, b) => a[0] - b[0])
    for (let k = 0; k < 3; k++) addEdge(i, d[k][1])
  }
  for (let s = 0; s < stemIdx.length - 1; s++) addEdge(stemIdx[s], stemIdx[s + 1])
  addEdge(stemIdx[0], 0)

  // ---- dinâmica ----
  const P: Params = { ...TARGET.idle }
  let pulses: Array<{ e: [number, number]; t: number; sp: number; hot: boolean }> = []
  let spawnAcc = 0
  let waves: Array<{ r: number; a: number }> = []
  let waveAcc = 0
  let bolts: number[][][] = []
  let boltTimer = 0
  let sparks: Array<{ t: number; sp: number; ox: number }> = []
  let sparkAcc = 0
  let t = 0
  let last = performance.now()
  let angle = 0
  let raf = 0

  const spawnPulse = () => pulses.push({ e: edges[(Math.random() * edges.length) | 0], t: 0, sp: rnd(1.2, 2.6), hot: Math.random() < 0.3 })

  function makeBolt(x1: number, y1: number, x2: number, y2: number): number[][] {
    const pts = [[x1, y1]]
    const seg = 10
    for (let i = 1; i < seg; i++) {
      const tt = i / seg
      const fall = 1 - Math.abs(2 * tt - 1)
      pts.push([lerp(x1, x2, tt) + rnd(-16, 16) * fall, lerp(y1, y2, tt) + rnd(-7, 7) * fall])
    }
    pts.push([x2, y2])
    return pts
  }

  const iso = (cx: number, cy: number, x: number, z: number, sc: number): [number, number] =>
    [cx + (x - z) * 0.86 * sc, cy + (x + z) * 0.52 * sc * 0.62]

  function drawChip(cx: number, cy: number, sc: number, glow: number) {
    ctx.save(); ctx.globalAlpha = 0.5
    const dirs = [[1, 0], [0, 1], [-1, 0], [0, -1], [1, 1], [-1, -1], [1, -1], [-1, 1]]
    for (const [dx, dz] of dirs) {
      const a1 = iso(cx, cy, dx * 78, dz * 78, sc), a2 = iso(cx, cy, dx * 150, dz * 150, sc)
      ctx.beginPath(); ctx.moveTo(a1[0], a1[1]); ctx.lineTo(a2[0], a2[1])
      ctx.strokeStyle = 'rgba(14,116,144,0.30)'; ctx.lineWidth = 1; ctx.stroke()
      ctx.beginPath(); ctx.arc(a2[0], a2[1], 2, 0, 6.29); ctx.fillStyle = 'rgba(34,211,238,0.35)'; ctx.fill()
    }
    ctx.restore()
    const ug = ctx.createRadialGradient(cx, cy, 0, cx, cy, 120 * sc / 0.55)
    ug.addColorStop(0, `rgba(8,145,178,${0.2 + 0.25 * glow})`); ug.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = ug; ctx.beginPath(); ctx.ellipse(cx, cy, 150 * sc / 0.55, 52 * sc / 0.55, 0, 0, 6.29); ctx.fill()
    ctx.beginPath()
    const cs = [iso(cx, cy, -70, -70, sc), iso(cx, cy, 70, -70, sc), iso(cx, cy, 70, 70, sc), iso(cx, cy, -70, 70, sc)]
    ctx.moveTo(cs[0][0], cs[0][1]); for (let i = 1; i < 4; i++) ctx.lineTo(cs[i][0], cs[i][1]); ctx.closePath()
    ctx.fillStyle = '#031018'; ctx.strokeStyle = 'rgba(34,211,238,0.55)'; ctx.lineWidth = 1.4; ctx.fill(); ctx.stroke()
    ctx.strokeStyle = 'rgba(34,211,238,0.40)'; ctx.lineWidth = 1.6
    for (let i = -2; i <= 2; i++) {
      const off = i * 26
      for (const [a, b] of [[[off, -70], [off, -92]], [[off, 70], [off, 92]], [[-70, off], [-92, off]], [[70, off], [92, off]]] as const) {
        const p = iso(cx, cy, a[0], a[1], sc), q = iso(cx, cy, b[0], b[1], sc)
        ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke()
      }
    }
    ctx.beginPath()
    const ds = [iso(cx, cy, -32, -32, sc), iso(cx, cy, 32, -32, sc), iso(cx, cy, 32, 32, sc), iso(cx, cy, -32, 32, sc)]
    ctx.moveTo(ds[0][0], ds[0][1]); for (let i = 1; i < 4; i++) ctx.lineTo(ds[i][0], ds[i][1]); ctx.closePath()
    ctx.fillStyle = '#041824'; ctx.strokeStyle = 'rgba(125,211,252,0.6)'; ctx.lineWidth = 1; ctx.fill(); ctx.stroke()
    const cg = ctx.createRadialGradient(cx, cy, 0, cx, cy, 26 + 10 * glow)
    cg.addColorStop(0, `rgba(255,220,170,${0.55 + 0.4 * glow})`)
    cg.addColorStop(0.35, `rgba(255,140,66,${0.3 + 0.35 * glow})`)
    cg.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(cx, cy, 26 + 10 * glow, 0, 6.29); ctx.fill()
  }

  function resize() {
    W = cv.clientWidth; H = Math.max(220, cv.clientHeight)
    cv.width = W * DPR; cv.height = H * DPR
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0)
  }
  const ro = new ResizeObserver(resize)
  ro.observe(cv)
  resize()

  function frame(now: number) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now; t += dt
    const tg = TARGET[mode], f = 1 - Math.pow(0.0018, dt)
    P.rot = lerp(P.rot, tg.rot, f); P.jit = lerp(P.jit, tg.jit, f); P.morph = lerp(P.morph, tg.morph, f)
    P.spawn = lerp(P.spawn, tg.spawn, f); P.edgeA = lerp(P.edgeA, tg.edgeA, f); P.coreI = lerp(P.coreI, tg.coreI, f)
    P.boltN = lerp(P.boltN, tg.boltN, f); P.boltA = lerp(P.boltA, tg.boltA, f)

    angle += P.rot * dt
    const breath = 1 + 0.016 * Math.sin(t * 0.9)
    let env = 0
    if (mode === 'speak') {
      if (extLevel > 0.01) {
        env = Math.min(1, extLevel)
      } else {
        env = Math.max(0, Math.sin(t * 7.3) + 0.55 * Math.sin(t * 19.1 + 1.3) + 0.35 * Math.sin(t * 3.7 + 0.5))
        env = Math.min(1, env * 0.62)
      }
    }
    const morphWave = P.morph * (0.5 + 0.5 * Math.sin(t * 1.6))
    let scl = Math.min(W, 640) * 0.265 * breath * (1 + 0.05 * env)
    scl = Math.min(scl, H * 0.34)
    const cx = W / 2, cy = H * 0.36
    const ca = Math.cos(angle), sa = Math.sin(angle)
    const pitch = 0.14, cp = Math.cos(pitch), sp = Math.sin(pitch)

    for (const n of nodes) {
      const jm = n.stem ? 0.25 : 1
      const jx = P.jit * jm * Math.sin(t * n.sp * 2.1 + n.ph) * n.dx
      const jy = P.jit * jm * Math.sin(t * n.sp * 1.7 + n.ph * 1.4) * n.dy
      const jz = P.jit * jm * Math.sin(t * n.sp * 2.5 + n.ph * 0.7) * n.dz
      const x = lerp(n.bx, n.ax, n.stem ? 0 : morphWave) + jx
      const y = lerp(n.by, n.ay, n.stem ? 0 : morphWave) + jy
      const z = lerp(n.bz, n.az, n.stem ? 0 : morphWave) + jz
      const px = x * ca + z * sa, pz = -x * sa + z * ca
      const py = y * cp - pz * sp, pz2 = y * sp + pz * cp
      n.depth = (pz2 + 1.4) / 2.8
      n.sx = cx + px * scl
      n.sy = cy - py * scl * 0.92
    }
    const stemEnd = nodes[stemIdx[stemIdx.length - 1]]

    ctx.clearRect(0, 0, W, H)

    const chipCx = W / 2, chipCy = H - Math.max(40, H * 0.115)
    const chipSc = Math.min(0.55, H / 1090)
    const glow = mode === 'think' ? 0.6 + 0.4 * Math.abs(Math.sin(t * 9)) : mode === 'speak' ? 0.3 + 0.7 * env : 0.25 + 0.1 * Math.sin(t * 1.2)
    drawChip(chipCx, chipCy, chipSc, glow)

    boltTimer -= dt
    if (boltTimer <= 0) {
      bolts = []
      const nb = Math.round(P.boltN + (mode === 'speak' ? env * 1.5 : 0))
      for (let b = 0; b < nb; b++) bolts.push(makeBolt(stemEnd.sx + rnd(-6, 6), stemEnd.sy, chipCx + rnd(-14, 14), chipCy - 6))
      boltTimer = rnd(0.05, 0.11)
    }
    for (const bp of bolts) {
      const ba = P.boltA * (mode === 'speak' ? 0.4 + 0.8 * env : 1)
      ctx.beginPath(); ctx.moveTo(bp[0][0], bp[0][1])
      for (let i = 1; i < bp.length; i++) ctx.lineTo(bp[i][0], bp[i][1])
      ctx.strokeStyle = `rgba(34,211,238,${(ba * 0.35).toFixed(3)})`; ctx.lineWidth = 3.2; ctx.stroke()
      ctx.beginPath(); ctx.moveTo(bp[0][0], bp[0][1])
      for (let i = 1; i < bp.length; i++) ctx.lineTo(bp[i][0], bp[i][1])
      ctx.strokeStyle = `rgba(220,250,255,${ba.toFixed(3)})`; ctx.lineWidth = 1.1; ctx.stroke()
    }

    sparkAcc += dt * (mode === 'think' ? 10 : mode === 'speak' ? 3 + 7 * env : 2)
    while (sparkAcc > 1) { sparkAcc -= 1; sparks.push({ t: 0, sp: rnd(0.5, 0.9), ox: rnd(-18, 18) }) }
    sparks = sparks.filter(sk => {
      sk.t += dt * sk.sp
      if (sk.t >= 1) return false
      const sx = lerp(chipCx + sk.ox, stemEnd.sx, sk.t)
      const sy = lerp(chipCy - 10, stemEnd.sy, sk.t) - 30 * Math.sin(Math.PI * sk.t)
      ctx.fillStyle = `rgba(125,211,252,${(0.7 * (1 - sk.t)).toFixed(3)})`
      ctx.beginPath(); ctx.arc(sx, sy, 1.6, 0, 6.29); ctx.fill()
      return true
    })

    waveAcc += dt
    if (mode === 'speak' && env > 0.55 && waveAcc > 0.22) { waves.push({ r: scl * 0.12, a: 0.5 }); waveAcc = 0 }
    waves = waves.filter(w => {
      w.r += dt * scl * 1.5; w.a -= dt * 0.55
      if (w.a <= 0) return false
      ctx.beginPath(); ctx.arc(cx, cy, w.r, 0, 6.29)
      ctx.strokeStyle = `rgba(255,140,66,${(w.a * 0.5).toFixed(3)})`; ctx.lineWidth = 1.5; ctx.stroke()
      ctx.beginPath(); ctx.arc(cx, cy, w.r * 1.06, 0, 6.29)
      ctx.strokeStyle = `rgba(34,211,238,${(w.a * 0.35).toFixed(3)})`; ctx.lineWidth = 1; ctx.stroke()
      return true
    })

    for (const [a, b] of edges) {
      const A = nodes[a], B = nodes[b]
      const dep = (A.depth + B.depth) / 2
      const al = P.edgeA * (0.25 + 0.75 * dep) * (mode === 'speak' ? 0.55 + 0.85 * env : 1)
      ctx.beginPath(); ctx.moveTo(A.sx, A.sy); ctx.lineTo(B.sx, B.sy)
      ctx.strokeStyle = `rgba(56,189,248,${al.toFixed(3)})`; ctx.lineWidth = 0.7 + dep * 0.7; ctx.stroke()
    }

    spawnAcc += dt * P.spawn
    while (spawnAcc > 1) { spawnAcc -= 1; spawnPulse() }
    pulses = pulses.filter(p => {
      p.t += dt * p.sp
      if (p.t >= 1) return false
      const A = nodes[p.e[0]], B = nodes[p.e[1]]
      const px = A.sx + (B.sx - A.sx) * p.t, py = A.sy + (B.sy - A.sy) * p.t
      const dep = (A.depth + B.depth) / 2, r = 1.6 + dep * 1.6
      const g = ctx.createRadialGradient(px, py, 0, px, py, r * 4)
      if (p.hot) { g.addColorStop(0, 'rgba(255,170,90,0.95)'); g.addColorStop(0.4, 'rgba(255,140,66,0.35)') }
      else { g.addColorStop(0, 'rgba(190,242,255,0.95)'); g.addColorStop(0.4, 'rgba(34,211,238,0.35)') }
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(px, py, r * 4, 0, 6.29); ctx.fill()
      return true
    })

    for (const n of nodes) {
      const r = 0.9 + n.depth * 1.9, al = 0.25 + 0.65 * n.depth
      ctx.fillStyle = `rgba(125,211,252,${(al * 0.9).toFixed(3)})`
      ctx.beginPath(); ctx.arc(n.sx, n.sy, r, 0, 6.29); ctx.fill()
    }

    const flick = mode === 'think' ? 0.85 + 0.15 * Math.sin(t * 23) + 0.08 * Math.sin(t * 41) : 1
    const coreR = scl * 0.15 * (1 + 0.35 * env) * flick
    const cg = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 2.6)
    cg.addColorStop(0, `rgba(255,214,150,${(0.95 * P.coreI).toFixed(3)})`)
    cg.addColorStop(0.25, `rgba(255,140,66,${(0.55 * P.coreI).toFixed(3)})`)
    cg.addColorStop(0.6, `rgba(255,107,0,${(0.18 * P.coreI).toFixed(3)})`)
    cg.addColorStop(1, 'rgba(0,0,0,0)')
    ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(cx, cy, coreR * 2.6, 0, 6.29); ctx.fill()

    raf = requestAnimationFrame(frame)
  }
  raf = requestAnimationFrame(frame)

  return {
    setMode(m: BrainMode) { mode = m },
    setLevel(l: number) { extLevel = l },
    destroy() { cancelAnimationFrame(raf); ro.disconnect() },
  }
}
