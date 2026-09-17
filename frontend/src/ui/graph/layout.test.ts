import { describe, expect, it } from 'vitest'
import type { Graph, GraphNode, Term } from '@/api/types'
import { layoutEtymologyGraph, sortLeaves } from './layout'

const leafA: Term = { lang: 'English', term: 'father' }
const leafB: Term = { lang: 'German', term: 'Vater' }

function node(id: string, role = 'ancestor'): GraphNode {
  const [lang, term] = id.split(':') as [string, string]
  return { id, lang, term, role }
}

describe('sortLeaves', () => {
  it('puts leafA first and leafB last among extra leaves', () => {
    const nodes = [
      node('Latin:pater', 'leaf'),
      node('German:Vater', 'leaf'),
      node('English:father', 'leaf'),
    ]
    expect(sortLeaves(nodes, leafA, leafB).map((item) => item.id)).toEqual([
      'English:father',
      'Latin:pater',
      'German:Vater',
    ])
  })
})

describe('layoutEtymologyGraph', () => {
  const graph: Graph = {
    nodes: [
      node('English:father', 'leaf'),
      node('German:Vater', 'leaf'),
      node('Proto-Germanic:*fader'),
    ],
    edges: [
      { from: 'English:father', to: 'Proto-Germanic:*fader' },
      { from: 'German:Vater', to: 'Proto-Germanic:*fader' },
      { from: 'English:father', to: 'missing:node' },
    ],
  }

  it('places leaves below ancestors and drops unknown edge ends', () => {
    const { nodes, edges } = layoutEtymologyGraph(graph, leafA, leafB)
    const yOf = Object.fromEntries(nodes.map((item) => [item.id, item.position.y]))
    expect(yOf['English:father']).toBeGreaterThan(yOf['Proto-Germanic:*fader'])
    expect(yOf['German:Vater']).toBe(yOf['English:father'])
    expect(edges.map((edge) => `${edge.source}->${edge.target}`)).toEqual([
      'English:father->Proto-Germanic:*fader',
      'German:Vater->Proto-Germanic:*fader',
    ])
  })
})
