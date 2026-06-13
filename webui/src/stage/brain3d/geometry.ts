// Geometria procedural do cérebro do Nox — pura e determinística (testável).
// Mesma forma aprovada no demo 2.5D: união de elipsoides (cérebro, lobos
// temporais, cerebelo) + córtex amostrado na casca + fissura longitudinal.

export interface BrainGeometry {
  count: number
  positions: Float32Array
  altPositions: Float32Array
  phases: Float32Array
  speeds: Float32Array
  jitterDirs: Float32Array
  isStem: Uint8Array
  edges: Uint32Array
  stemTipIndex: number
}

// PRNG determinístico (mulberry32)
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function insideBrain(x: number, y: number, z: number): boolean {
  let inCer = ((x - 0.06) ** 2) / 1.21 + ((y - 0.16) ** 2) / 0.4356 + (z * z) / 0.5476 <= 1
  if (inCer && y < -0.34) inCer = false
  const inT1 = ((x - 0.18) ** 2) / 0.2704 + ((y + 0.22) ** 2) / 0.0729 + ((z - 0.46) ** 2) / 0.0729 <= 1
  const inT2 = ((x - 0.18) ** 2) / 0.2704 + ((y + 0.22) ** 2) / 0.0729 + ((z + 0.46) ** 2) / 0.0729 <= 1
  const inCb = ((x + 0.74) ** 2) / 0.1156 + ((y + 0.4) ** 2) / 0.0576 + (z * z) / 0.16 <= 1
  return inCer || inT1 || inT2 || inCb
}

export const inFissure = (_x: number, y: number, z: number): boolean =>
  Math.abs(z) < 0.055 && y > 0.28

const CENTER = { x: 0, y: -0.04, z: 0 }

export function radiusInDir(dx: number, dy: number, dz: number): number {
  let lo = 0
  let hi = 2.2
  for (let i = 0; i < 16; i++) {
    const m = (lo + hi) / 2
    if (insideBrain(CENTER.x + dx * m, CENTER.y + dy * m, CENTER.z + dz * m)) lo = m
    else hi = m
  }
  return lo
}

export const gyri = (x: number, y: number, z: number): number =>
  1 + 0.05 * Math.sin(6 * Math.atan2(z, x) + 2.2 * y) * Math.cos(5.1 * y + 1.3)

const STEM_COUNT = 7

export function buildBrainGeometry(n = 900, seed = 1337): BrainGeometry {
  const rng = mulberry32(seed)
  const rnd = (a: number, b: number) => a + rng() * (b - a)
  const lerp = (a: number, b: number, f: number) => a + (b - a) * f

  const pos: number[] = []
  const alt: number[] = []
  const phases: number[] = []
  const speeds: number[] = []
  const jit: number[] = []
  const stemFlags: number[] = []

  let tries = 0
  let placed = 0
  while (placed < n && tries < n * 120) {
    tries++
    let x: number, y: number, z: number
    if (rng() < 0.64) {
      let dx = rnd(-1, 1)
      let dy = rnd(-1, 1)
      let dz = rnd(-1, 1)
      const L = Math.hypot(dx, dy, dz)
      if (L < 0.001) continue
      dx /= L; dy /= L; dz /= L
      const R = radiusInDir(dx, dy, dz)
      if (R < 0.15) continue
      const rr = R * rnd(0.88, 1.0)
      x = CENTER.x + dx * rr
      y = CENTER.y + dy * rr
      z = CENTER.z + dz * rr
      const g = gyri(x, y, z)
      x *= g; y *= g; z *= g
    } else {
      x = rnd(-1.25, 1.25)
      y = rnd(-0.85, 0.95)
      z = rnd(-0.85, 0.85)
      if (!insideBrain(x, y, z)) continue
    }
    if (inFissure(x, y, z)) continue
    pos.push(x, y, z)
    alt.push(x * 1.15 + 0.09 * Math.sin(7 * y), y * 1.09 + 0.07 * Math.sin(6 * x), z * 1.2)
    phases.push(rng() * Math.PI * 2)
    speeds.push(rnd(0.5, 1.4))
    jit.push(rnd(-1, 1), rnd(-1, 1), rnd(-1, 1))
    stemFlags.push(0)
    placed++
  }

  // tronco cerebral: cadeia descendo até o ponto de conexão com o chip
  for (let s = 0; s < STEM_COUNT; s++) {
    const tt = s / (STEM_COUNT - 1)
    const x = lerp(-0.18, -0.02, tt) + 0.04 * Math.sin(tt * 3)
    const y = lerp(-0.34, -1.05, tt)
    pos.push(x, y, 0)
    alt.push(x, y, 0)
    phases.push(rng() * Math.PI * 2)
    speeds.push(0.6)
    jit.push(0.2, 0.1, 0.2)
    stemFlags.push(1)
  }

  const count = placed + STEM_COUNT

  // Arestas CURTAS: vizinho mais próximo garantido + até 4 vizinhos dentro do
  // raio de corte. Arestas longas (kNN puro) atravessavam o volume e davam
  // aparência de wireframe de poliedro; o corte por raio abraça o córtex.
  const R_CUT = 0.21
  const R2 = R_CUT * R_CUT
  const MAX_PER_NODE = 4
  const edgePairs: number[] = []
  const seen = new Set<number>()
  const addEdge = (a: number, b: number) => {
    const key = a < b ? a * count + b : b * count + a
    if (!seen.has(key) && a !== b) {
      seen.add(key)
      edgePairs.push(Math.min(a, b), Math.max(a, b))
    }
  }
  for (let i = 0; i < placed; i++) {
    const ix = pos[i * 3], iy = pos[i * 3 + 1], iz = pos[i * 3 + 2]
    let nearest = -1
    let nearestD = Infinity
    const near: Array<[number, number]> = []
    for (let j = 0; j < placed; j++) {
      if (i === j) continue
      const dx = ix - pos[j * 3]
      const dy = iy - pos[j * 3 + 1]
      const dz = iz - pos[j * 3 + 2]
      const d = dx * dx + dy * dy + dz * dz
      if (d < nearestD) { nearestD = d; nearest = j }
      if (d <= R2) near.push([d, j])
    }
    near.sort((a, b) => a[0] - b[0])
    for (let k = 0; k < Math.min(MAX_PER_NODE, near.length); k++) addEdge(i, near[k][1])
    if (near.length === 0 && nearest >= 0) addEdge(i, nearest) // nó nunca fica isolado
  }
  for (let s = 0; s < STEM_COUNT - 1; s++) addEdge(placed + s, placed + s + 1)
  addEdge(placed, 0)

  return {
    count,
    positions: new Float32Array(pos),
    altPositions: new Float32Array(alt),
    phases: new Float32Array(phases),
    speeds: new Float32Array(speeds),
    jitterDirs: new Float32Array(jit),
    isStem: new Uint8Array(stemFlags),
    edges: new Uint32Array(edgePairs),
    stemTipIndex: count - 1,
  }
}
