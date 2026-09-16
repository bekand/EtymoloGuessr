import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { joinClasses } from '@/utils/joinClasses'
import type { EtymologyNodeData } from './layout'
import './EtymologyNode.scss'

export type EtymologyFlowNode = Node<EtymologyNodeData, 'etymology'>

export function EtymologyNode({ data, isConnectable }: NodeProps<EtymologyFlowNode>) {
  return (
    <article className={joinClasses('etymologyNode', data.role, isConnectable && 'connectable')}>
      <Handle type="target" position={Position.Bottom} isConnectable={isConnectable} />
      {data.lang ? <span className="lang">{data.lang}</span> : null}
      <h3 className="term">{data.term}</h3>
      {data.gloss ? <p className="gloss">{data.gloss}</p> : null}
      <Handle type="source" position={Position.Top} isConnectable={isConnectable} />
    </article>
  )
}
