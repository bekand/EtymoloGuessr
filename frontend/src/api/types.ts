export type Term = {
  lang: string
  term: string
  gloss?: string | null
}

export type Choice = {
  id: string
  gloss: string
}

export type GraphNode = {
  id: string
  lang: string
  term: string
  gloss?: string | null
  role: string
}

export type GraphEdge = {
  from: string
  to: string
  reltype?: string | null
}

export type Graph = {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type PuzzlePrompt = {
  id: string
  mode: 'easy' | 'hard'
  langPair: string
  leafA: Term
  leafB: Term
  choices: Choice[]
  promptGraph?: Graph
}

export type SolveResponse = {
  correct: boolean
  correctChoice: string
  choices: Choice[]
  goldGraph: Graph
}

export type PuzzleMode = PuzzlePrompt['mode']
