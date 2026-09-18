import type { AnimationEventHandler, CSSProperties, ReactNode } from 'react'
import { joinClasses } from '@/utils/joinClasses'
import './Sheet.scss'

type SheetTone = 'paper' | 'kraft'

type SheetProps = {
  children: ReactNode
  tone?: SheetTone
  className?: string
  style?: CSSProperties
  as?: 'main' | 'section' | 'div'
  onAnimationEnd?: AnimationEventHandler<HTMLElement>
}

export function Sheet({
  children,
  tone = 'paper',
  className,
  style,
  as: Tag = 'div',
  onAnimationEnd,
}: SheetProps) {
  const classes = joinClasses('sheet', tone, className)

  return (
    <Tag className={classes} style={style} onAnimationEnd={onAnimationEnd}>
      {children}
    </Tag>
  )
}
