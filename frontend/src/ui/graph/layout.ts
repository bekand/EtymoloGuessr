import type { Graph, GraphNode, Term } from '@/api/types'
import { Position, type Edge, type Node } from '@xyflow/react'

export const NODE_WIDTH = 176
export const NODE_HEIGHT = 124
const H_GAP = 40
const V_GAP = 96
const PAD = 24

export type EtymologyNodeData = {
  lang: string
  term: string
  gloss?: string | null
  role: string
}

function nodeKey(term: Term): string {
  return `${term.lang}:${term.term}`
}

function longestPathFromLeaves(graph: Graph): Map<string, number> {
  const ids = new Set(graph.nodes.map((node) => node.id))
  const outgoing = new Map<string, string[]>()
  const incomingCount = new Map<string, number>()

  for (const id of ids) {
    outgoing.set(id, [])
    incomingCount.set(id, 0)
  }

  for (const edge of graph.edges) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) {
      continue
    }
    outgoing.get(edge.from)?.push(edge.to)
    incomingCount.set(edge.to, (incomingCount.get(edge.to) ?? 0) + 1)
  }

  const rank = new Map<string, number>()
  const queue: string[] = []
  for (const id of ids) {
    if ((incomingCount.get(id) ?? 0) === 0) {
      rank.set(id, 0)
      queue.push(id)
    }
  }

  if (queue.length === 0) {
    for (const id of ids) {
      rank.set(id, 0)
    }
    return rank
  }

  while (queue.length > 0) {
    const id = queue.shift()
    if (!id) {
      break
    }
    const nextRank = (rank.get(id) ?? 0) + 1
    for (const to of outgoing.get(id) ?? []) {
      rank.set(to, Math.max(rank.get(to) ?? 0, nextRank))
      incomingCount.set(to, (incomingCount.get(to) ?? 1) - 1)
      if ((incomingCount.get(to) ?? 0) === 0) {
        queue.push(to)
      }
    }
  }

  for (const id of ids) {
    if (!rank.has(id)) {
      rank.set(id, 0)
    }
  }

  return rank
}

function sortLeaves(nodes: GraphNode[], leafA?: Term, leafB?: Term): GraphNode[] {
  const aId = leafA ? nodeKey(leafA) : undefined
  const bId = leafB ? nodeKey(leafB) : undefined
  return [...nodes].sort((left, right) => {
    if (left.id === aId) {
      return -1
    }
    if (right.id === aId) {
      return 1
    }
    if (left.id === bId) {
      return 1
    }
    if (right.id === bId) {
      return -1
    }
    return left.id.localeCompare(right.id)
  })
}

export function layoutEtymologyGraph(
  graph: Graph,
  leafA?: Term,
  leafB?: Term,
): { nodes: Node<EtymologyNodeData, 'etymology'>[]; edges: Edge[] } {
  const ranks = longestPathFromLeaves(graph)
  const maxRank = Math.max(0, ...ranks.values())
  const byRank = new Map<number, GraphNode[]>()

  for (const node of graph.nodes) {
    const rank = ranks.get(node.id) ?? 0
    const bucket = byRank.get(rank) ?? []
    bucket.push(node)
    byRank.set(rank, bucket)
  }

  const xOf = new Map<string, number>()
  const yOf = new Map<string, number>()

  for (let rank = 0; rank <= maxRank; rank++) {
    const layer = byRank.get(rank) ?? []
    const ordered = rank === 0 ? sortLeaves(layer, leafA, leafB) : [...layer].sort((a, b) => a.id.localeCompare(b.id))

    if (rank === 0) {
      ordered.forEach((node, index) => {
        xOf.set(node.id, PAD + index * (NODE_WIDTH + H_GAP))
      })
    } else {
      ordered.forEach((node) => {
        const childXs = graph.edges
          .filter((edge) => edge.to === node.id)
          .map((edge) => xOf.get(edge.from))
          .filter((value): value is number => value !== undefined)
        xOf.set(
          node.id,
          childXs.length > 0 ? childXs.reduce((sum, value) => sum + value, 0) / childXs.length : PAD,
        )
      })
      const sorted = [...ordered].sort((a, b) => (xOf.get(a.id) ?? 0) - (xOf.get(b.id) ?? 0))
      let cursor = PAD
      for (const node of sorted) {
        const next = Math.max(xOf.get(node.id) ?? cursor, cursor)
        xOf.set(node.id, next)
        cursor = next + NODE_WIDTH + H_GAP
      }
    }

    const y = PAD + (maxRank - rank) * (NODE_HEIGHT + V_GAP)
    for (const node of ordered) {
      yOf.set(node.id, y)
    }
  }

  const xs = [...xOf.values()]
  const minX = xs.length ? Math.min(...xs) : 0
  for (const [id, x] of xOf) {
    xOf.set(id, x - minX + PAD)
  }

  const nodes: Node<EtymologyNodeData, 'etymology'>[] = graph.nodes.map((node) => ({
    id: node.id,
    type: 'etymology',
    position: { x: xOf.get(node.id) ?? PAD, y: yOf.get(node.id) ?? PAD },
    data: {
      lang: node.lang,
      term: node.term,
      gloss: node.gloss,
      role: node.role,
    },
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    draggable: false,
    selectable: false,
    sourcePosition: Position.Top,
    targetPosition: Position.Bottom,
    style: { width: NODE_WIDTH, height: NODE_HEIGHT },
  }))

  const known = new Set(graph.nodes.map((node) => node.id))
  const edges: Edge[] = graph.edges
    .filter((edge) => known.has(edge.from) && known.has(edge.to))
    .map((edge) => ({
      id: `${edge.from}->${edge.to}`,
      source: edge.from,
      target: edge.to,
      type: 'ink',
      label: edge.reltype ?? undefined,
      data: { reltype: edge.reltype ?? undefined },
    }))

  return { nodes, edges }
}
