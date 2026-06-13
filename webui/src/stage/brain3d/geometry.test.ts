import { describe, expect, it } from 'vitest'
import { buildBrainGeometry, inFissure, mulberry32 } from './geometry'

describe('buildBrainGeometry', () => {
  const g = buildBrainGeometry(400, 42)

  it('gera a contagem pedida + 7 nós de tronco', () => {
    expect(g.count).toBe(407)
    expect(g.positions.length).toBe(407 * 3)
    expect(g.altPositions.length).toBe(407 * 3)
    expect(g.isStem.filter(v => v === 1).length).toBe(7)
  })

  it('nenhum nó dentro da fissura longitudinal', () => {
    for (let i = 0; i < g.count; i++) {
      if (g.isStem[i]) continue
      const x = g.positions[i * 3]
      const y = g.positions[i * 3 + 1]
      const z = g.positions[i * 3 + 2]
      expect(inFissure(x, y, z)).toBe(false)
    }
  })

  it('posições finitas e limitadas', () => {
    for (const v of g.positions) {
      expect(Number.isFinite(v)).toBe(true)
      expect(Math.abs(v)).toBeLessThan(1.6)
    }
  })

  it('arestas válidas: pares, sem self-loop, sem duplicata, índices no range', () => {
    expect(g.edges.length % 2).toBe(0)
    const seen = new Set<string>()
    for (let e = 0; e < g.edges.length; e += 2) {
      const a = g.edges[e]
      const b = g.edges[e + 1]
      expect(a).not.toBe(b)
      expect(a).toBeLessThan(g.count)
      expect(b).toBeLessThan(g.count)
      const k = `${a}-${b}`
      expect(seen.has(k)).toBe(false)
      seen.add(k)
    }
  })

  it('nenhum nó do córtex fica isolado', () => {
    const connected = new Set<number>()
    for (let e = 0; e < g.edges.length; e++) connected.add(g.edges[e])
    for (let i = 0; i < g.count; i++) {
      if (g.isStem[i]) continue
      expect(connected.has(i)).toBe(true)
    }
  })

  it('arestas são curtas (raio de corte) exceto resgates de isolamento', () => {
    let longas = 0
    for (let e = 0; e < g.edges.length; e += 2) {
      const a = g.edges[e] * 3
      const b = g.edges[e + 1] * 3
      if (g.isStem[g.edges[e]] || g.isStem[g.edges[e + 1]]) continue
      const d = Math.hypot(
        g.positions[a] - g.positions[b],
        g.positions[a + 1] - g.positions[b + 1],
        g.positions[a + 2] - g.positions[b + 2],
      )
      if (d > 0.30) longas++
    }
    // resgates de nó isolado podem gerar poucas arestas longas; nunca mais que 5%
    expect(longas).toBeLessThan(g.edges.length / 2 * 0.05)
  })

  it('tronco encadeado: 6 arestas consecutivas + ponte para o córtex', () => {
    const stemStart = g.count - 7
    const pairs = new Set<string>()
    for (let e = 0; e < g.edges.length; e += 2) pairs.add(`${g.edges[e]}-${g.edges[e + 1]}`)
    for (let s = 0; s < 6; s++) {
      expect(pairs.has(`${stemStart + s}-${stemStart + s + 1}`)).toBe(true)
    }
    expect(pairs.has(`0-${stemStart}`)).toBe(true)
    expect(g.stemTipIndex).toBe(g.count - 1)
  })

  it('determinístico por seed', () => {
    const a = buildBrainGeometry(200, 7)
    const b = buildBrainGeometry(200, 7)
    const c = buildBrainGeometry(200, 8)
    expect(a.positions).toEqual(b.positions)
    expect(a.positions).not.toEqual(c.positions)
  })
})

describe('mulberry32', () => {
  it('sequência estável em [0,1)', () => {
    const r = mulberry32(123)
    const seq = [r(), r(), r()]
    const r2 = mulberry32(123)
    expect([r2(), r2(), r2()]).toEqual(seq)
    for (const v of seq) {
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThan(1)
    }
  })
})
