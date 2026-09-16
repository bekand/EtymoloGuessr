import { BaseEdge, EdgeLabelRenderer, type Edge, type EdgeProps } from '@xyflow/react'
import './InkEdge.scss'

export type InkEdgeData = {
  reltype?: string
}

export type InkFlowEdge = Edge<InkEdgeData, 'ink'>

function inkSeed(id: string): number {
  let hash = 2166136261
  for (let i = 0; i < id.length; i += 1) {
    hash ^= id.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash
}

function wobble(seed: number, span: number): number {
  const unit = ((seed >>> 0) % 1000) / 1000
  return (unit - 0.5) * span
}

function formatReltype(reltype?: string): string {
  return (reltype ?? '').replaceAll('_', ' ').trim()
}

export function InkEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style,
  markerEnd,
  data,
  label,
}: EdgeProps<InkFlowEdge>) {
  const seed = inkSeed(id)
  const midX = (sourceX + targetX) / 2 + wobble(seed, 18)
  const midY = (sourceY + targetY) / 2 + wobble(seed >> 3, 14)
  const c1x = sourceX + (midX - sourceX) * 0.55 + wobble(seed >> 6, 10)
  const c1y = sourceY + (midY - sourceY) * 0.35 + wobble(seed >> 9, 12)
  const c2x = midX + (targetX - midX) * 0.45 + wobble(seed >> 12, 10)
  const c2y = midY + (targetY - midY) * 0.55 + wobble(seed >> 15, 12)
  const path = `M ${sourceX} ${sourceY} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${targetX} ${targetY}`

  const reltype = formatReltype(
    (typeof label === 'string' ? label : undefined) ?? data?.reltype,
  )
  const dx = targetX - sourceX
  const dy = targetY - sourceY
  const len = Math.hypot(dx, dy) || 1
  const offset = 10 + wobble(seed >> 4, 6)
  const labelX = midX - (dy / len) * offset
  const labelY = midY + (dx / len) * offset
  const tilt = wobble(seed >> 8, 6)

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className="inkEdge"
        style={{
          stroke: 'var(--ink-muted)',
          strokeWidth: 1.6,
          strokeLinecap: 'round',
          fill: 'none',
          ...style,
        }}
      />
      {reltype ? (
        <EdgeLabelRenderer>
          <span
            className="inkEdgeLabel nodrag nopan"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px) rotate(${tilt}deg)`,
            }}
          >
            {reltype}
          </span>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
}
