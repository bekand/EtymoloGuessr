import { Background, MarkerType, ReactFlow } from '@xyflow/react'
import type { Graph, Term } from '@/api/types'
import { EtymologyNode } from './EtymologyNode'
import { InkEdge } from './InkEdge'
import { layoutEtymologyGraph } from './layout'
import '@xyflow/react/dist/style.css'
import './EtymologyGraph.scss'

const nodeTypes = { etymology: EtymologyNode }
const edgeTypes = { ink: InkEdge }
const inkMarker = {
  type: MarkerType.ArrowClosed,
  width: 14,
  height: 14,
  color: '#2e2a26',
} as const

type EtymologyGraphProps = {
  graph: Graph
  leafA?: Term
  leafB?: Term
}

export function EtymologyGraph({ graph, leafA, leafB }: EtymologyGraphProps) {
  const { nodes, edges } = layoutEtymologyGraph(graph, leafA, leafB)
  const markedEdges = edges.map((edge) => ({
    ...edge,
    markerEnd: inkMarker,
  }))

  return (
    <div className="etymologyGraph" role="img" aria-label="Etymology relationships">
      <ReactFlow
        nodes={nodes}
        edges={markedEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.18, minZoom: 0.4, maxZoom: 1.05 }}
        minZoom={0.4}
        maxZoom={1.25}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll={false}
        zoomOnPinch
        preventScrolling={false}
      >
        <Background color="var(--rule)" gap={24} size={1} />
      </ReactFlow>
    </div>
  )
}
