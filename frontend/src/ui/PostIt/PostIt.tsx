import type { ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './PostIt.module.css'

type PostItTone = 'yellow' | 'pink' | 'blue' | 'green'

type PostItProps = {
  children?: ReactNode
  tone?: PostItTone
  selected?: boolean
  placeholder?: boolean
  className?: string
} & ButtonHTMLAttributes<HTMLButtonElement>

const toneClass: Record<PostItTone, string> = {
  yellow: styles.yellow,
  pink: styles.pink,
  blue: styles.blue,
  green: styles.green,
}

export function PostIt({
  children,
  tone = 'yellow',
  selected = false,
  placeholder = false,
  className,
  type = 'button',
  ...rest
}: PostItProps) {
  const classes = [
    styles.note,
    toneClass[tone],
    selected ? styles.selected : '',
    placeholder ? styles.placeholder : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button type={type} className={classes} aria-pressed={selected} {...rest}>
      {placeholder && !children ? <span className={styles.lines} aria-hidden="true" /> : children}
    </button>
  )
}
