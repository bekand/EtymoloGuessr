import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import type { EtymologyNodeData } from './layout'
import './EtymologyNode.scss'

export type EtymologyFlowNode = Node<EtymologyNodeData, 'etymology'>

export function EtymologyNode({ data }: NodeProps<EtymologyFlowNode>) {
  return (
    <article className={`etymologyNode ${data.role}`}>
      <Handle type="target" position={Position.Bottom} isConnectable={false} />
      {data.lang ? <span className="lang">{data.lang}</span> : null}
      <h3 className="term">{data.term}</h3>
      {data.gloss ? <p className="gloss">{data.gloss}</p> : null}
      <Handle type="source" position={Position.Top} isConnectable={false} />
    </article>
  )
}
