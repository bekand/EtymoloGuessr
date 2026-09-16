import type { CSSProperties, ReactNode } from 'react'
import styles from './Sheet.module.css'

type SheetTone = 'paper' | 'ruled' | 'kraft' | 'blotter'

type SheetProps = {
  children: ReactNode
  tone?: SheetTone
  className?: string
  style?: CSSProperties
  as?: 'main' | 'section' | 'div'
}

export function Sheet({
  children,
  tone = 'paper',
  className,
  style,
  as: Tag = 'div',
}: SheetProps) {
  const classes = [styles.sheet, styles[tone], className].filter(Boolean).join(' ')

  return (
    <Tag className={classes} style={style}>
      {children}
    </Tag>
  )
}
