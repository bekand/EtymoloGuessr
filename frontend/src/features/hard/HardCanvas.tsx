import { useEffect, useImperativeHandle, useRef, useState, type DragEvent, type Ref } from 'react'
import {
  Background,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useNodesInitialized,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
} from '@xyflow/react'
import type { Graph, GraphEdge, GraphNode, Term } from '@/api/types'
import { PostIt } from '@/ui'
import { EtymologyNode, type EtymologyFlowNode } from '@/ui/graph/EtymologyNode'
import { InkEdge } from '@/ui/graph/InkEdge'
import {
  H_GAP,
  NODE_HEIGHT,
  NODE_WIDTH,
  PAD,
  sortLeaves,
  type EtymologyNodeData,
} from '@/ui/graph/layout'
import { shuffle } from '@/utils/shuffle'
import '@xyflow/react/dist/style.css'
import '@/ui/graph/EtymologyGraph.scss'

const nodeTypes = { etymology: EtymologyNode }
const edgeTypes = { ink: InkEdge }
const PALETTE_TONES = ['yellow', 'pink', 'blue', 'green'] as const
const NODE_MIME = 'application/etymologuessr-node'

const inkMarker = {
  type: MarkerType.ArrowClosed,
  width: 14,
  height: 14,
  color: '#2e2a26',
} as const

const fitPlacedView = { padding: 0.3, duration: 220, minZoom: 0.4, maxZoom: 1.05 } as const

export type HardCanvasHandle = {
  getGraphEdges: () => GraphEdge[]
}

type HardCanvasProps = {
  graph: Graph
  leafA?: Term
  leafB?: Term
  disabled?: boolean
  onAllPlacedChange?: (allPlaced: boolean) => void
  ref?: Ref<HardCanvasHandle>
}

function toFlowNode(
  node: GraphNode,
  position: { x: number; y: number },
  draggable: boolean,
): EtymologyFlowNode {
  return {
    id: node.id,
    type: 'etymology',
    position,
    data: {
      lang: node.lang,
      term: node.term,
      gloss: node.gloss,
      role: node.role,
    },
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    draggable,
    selectable: draggable,
    sourcePosition: Position.Top,
    targetPosition: Position.Bottom,
    style: { width: NODE_WIDTH, height: NODE_HEIGHT },
  }
}

function paletteNodes(graph: Graph, leafA?: Term, leafB?: Term): GraphNode[] {
  const leaves = sortLeaves(
    graph.nodes.filter((node) => node.role === 'leaf'),
    leafA,
    leafB,
  )
  const rest = graph.nodes
    .filter((node) => node.role !== 'leaf')
    .slice()
    .sort((left, right) => left.id.localeCompare(right.id))
  return [...leaves, ...rest]
}

function nextPlacePosition(placedCount: number): { x: number; y: number } {
  const col = placedCount % 3
  const row = Math.floor(placedCount / 3)
  return {
    x: PAD + col * (NODE_WIDTH + H_GAP),
    y: PAD + row * (NODE_HEIGHT + 40),
  }
}

function toGraphEdges(edges: Edge[]): GraphEdge[] {
  return edges.map((edge) => ({ from: edge.source, to: edge.target }))
}

function tryFitPlacedNodes(
  pendingFitRef: { current: boolean },
  storeNodes: Node[],
  expectedCount: number,
  fitView: (options: typeof fitPlacedView) => unknown,
) {
  if (!pendingFitRef.current) {
    return
  }
  if (storeNodes.length < expectedCount) {
    return
  }
  const measured = storeNodes.every(
    (node) => (node.measured?.width ?? node.width) && (node.measured?.height ?? node.height),
  )
  if (!measured) {
    return
  }
  pendingFitRef.current = false
  void fitView(fitPlacedView)
}

function HardCanvasBoard({
  graph,
  leafA,
  leafB,
  disabled,
  onAllPlacedChange,
  canvasRef,
}: Omit<HardCanvasProps, 'ref'> & { canvasRef?: Ref<HardCanvasHandle> }) {
  const { screenToFlowPosition, fitView, getEdges, getNodes } = useReactFlow()
  const nodesInitialized = useNodesInitialized()
  const pendingFitRef = useRef(false)
  const shuffleSeed = graph.nodes.map((node) => node.id).join('|')
  const cards = shuffle(paletteNodes(graph, leafA, leafB), shuffleSeed)
  const cardById = new Map(graph.nodes.map((node) => [node.id, node]))
  const tones = shuffle(PALETTE_TONES, shuffleSeed)

  const [nodes, setNodes] = useState<Node<EtymologyNodeData, 'etymology'>[]>([])
  const [edges, setEdges] = useState<Edge[]>([])

  const placedIds = new Set(nodes.map((node) => node.id))
  const allPlaced = graph.nodes.length > 0 && nodes.length === graph.nodes.length

  useEffect(() => {
    onAllPlacedChange?.(allPlaced)
  }, [allPlaced, onAllPlacedChange])

  useImperativeHandle(
    canvasRef,
    () => ({
      getGraphEdges: () => {
        const live = getEdges()
        return toGraphEdges(live.length > 0 ? live : edges)
      },
    }),
    [edges, getEdges],
  )

  useEffect(() => {
    if (!nodesInitialized) {
      return
    }
    tryFitPlacedNodes(pendingFitRef, getNodes(), nodes.length, fitView)
  }, [fitView, getNodes, nodes, nodesInitialized])

  const placeNode = (id: string, position?: { x: number; y: number }) => {
    const card = cardById.get(id)
    if (!card || disabled) {
      return
    }
    setNodes((current) => {
      if (current.some((node) => node.id === id)) {
        return current
      }
      const nextPos = position ?? nextPlacePosition(current.length)
      pendingFitRef.current = true
      return [...current, toFlowNode(card, nextPos, true)]
    })
  }

  const unplaceNode = (id: string) => {
    if (disabled || !placedIds.has(id)) {
      return
    }
    setNodes((current) => current.filter((node) => node.id !== id))
    setEdges((current) => current.filter((edge) => edge.source !== id && edge.target !== id))
  }

  const onNodesChangeHandler: OnNodesChange<EtymologyFlowNode> = (changes) => {
    if (disabled) {
      return
    }
    setNodes((current) => applyNodeChanges(changes, current))
    if (changes.some((change) => change.type === 'dimensions')) {
      tryFitPlacedNodes(pendingFitRef, getNodes(), nodes.length, fitView)
    }
  }

  const onEdgesChangeHandler: OnEdgesChange = (changes) => {
    if (disabled) {
      return
    }
    setEdges((current) => applyEdgeChanges(changes, current))
  }

  const onConnect: OnConnect = (connection: Connection) => {
    if (disabled || !connection.source || !connection.target || connection.source === connection.target) {
      return
    }
    setEdges((current) => {
      const duplicate = current.some(
        (edge) => edge.source === connection.source && edge.target === connection.target,
      )
      if (duplicate) {
        return current
      }
      return addEdge(
        {
          ...connection,
          type: 'ink',
          markerEnd: inkMarker,
        },
        current,
      )
    })
  }

  const handleDrop = (event: DragEvent) => {
    event.preventDefault()
    const id = event.dataTransfer.getData(NODE_MIME)
    if (!id) {
      return
    }
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
    placeNode(id, {
      x: position.x - NODE_WIDTH / 2,
      y: position.y - NODE_HEIGHT / 2,
    })
  }

  return (
    <div className="hardPlay">
      <section className="palette" aria-label="Word cards">
        <p className="sectionLabel">Terms</p>
        <div className="notes">
          {cards.map((card, index) => {
            const placed = placedIds.has(card.id)
            return (
              <PostIt
                key={card.id}
                tone={tones[index % tones.length]}
                selected={placed}
                disabled={disabled}
                draggable={!placed && !disabled}
                aria-label={
                  placed
                    ? `Return ${card.term} to the palette`
                    : `Place ${card.lang} ${card.term}`
                }
                onDragStart={(event) => {
                  event.dataTransfer.setData(NODE_MIME, card.id)
                  event.dataTransfer.effectAllowed = 'move'
                }}
                onClick={() => {
                  if (placed) {
                    unplaceNode(card.id)
                  } else {
                    placeNode(card.id)
                  }
                }}
              >
                <span className="paletteLang">{card.lang}</span>
                {card.term}
              </PostIt>
            )
          })}
        </div>
        <p className="paletteHint">
          Drag onto the blotter or tap to place. Tap again to take back.
        </p>
      </section>

      <div
        className="etymologyGraph hardBoard"
        onDragOver={(event) => {
          event.preventDefault()
          event.dataTransfer.dropEffect = 'move'
        }}
        onDrop={handleDrop}
      >
        {nodes.length === 0 ? (
          <p className="emptyBoard" aria-hidden="true">
            Drop cards here
          </p>
        ) : null}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChangeHandler}
          onEdgesChange={onEdgesChangeHandler}
          onConnect={onConnect}
          onEdgeClick={(_, edge) => {
            if (!disabled) {
              setEdges((current) => current.filter((item) => item.id !== edge.id))
            }
          }}
          fitView
          fitViewOptions={{ padding: 0.2, minZoom: 0.4, maxZoom: 1.05 }}
          minZoom={0.4}
          maxZoom={1.25}
          nodesDraggable={!disabled}
          nodesConnectable={!disabled}
          elementsSelectable={!disabled}
          panOnDrag
          zoomOnScroll={false}
          zoomOnPinch
          deleteKeyCode={['Backspace', 'Delete']}
          connectionLineStyle={{ stroke: 'var(--ink-muted)', strokeWidth: 1.6 }}
          defaultEdgeOptions={{ type: 'ink', markerEnd: inkMarker }}
        >
          <Background color="var(--rule)" gap={24} size={1} />
        </ReactFlow>
      </div>
    </div>
  )
}

export function HardCanvas({ ref, ...props }: HardCanvasProps) {
  return (
    <ReactFlowProvider>
      <HardCanvasBoard {...props} canvasRef={ref} />
    </ReactFlowProvider>
  )
}
