import type { AnimationEventHandler, CSSProperties, ReactNode } from 'react'
import { joinClasses } from '@/utils/joinClasses'
import './Sheet.scss'

type SheetTone = 'paper' | 'kraft'

type SheetProps = {
  children: ReactNode
  header?: ReactNode
  instruction?: ReactNode
  tone?: SheetTone
  className?: string
  style?: CSSProperties
  as?: 'main' | 'section' | 'div'
  onAnimationEnd?: AnimationEventHandler<HTMLElement>
}

export function Sheet({
  children,
  header,
  instruction,
  tone = 'paper',
  className,
  style,
  as: Tag = 'div',
  onAnimationEnd,
}: SheetProps) {
  const classes = joinClasses('sheet', tone, className)

  return (
    <Tag className={classes} style={style} onAnimationEnd={onAnimationEnd}>
      {header}
      {instruction ? <p className="instruction">{instruction}</p> : null}
      {children}
    </Tag>
  )
}
