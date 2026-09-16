import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './PostIt.scss'

type PostItTone = 'yellow' | 'pink' | 'blue' | 'green'

type PostItProps = {
  children?: ReactNode
  tone?: PostItTone
  marker?: string
  selected?: boolean
  placeholder?: boolean
  className?: string
} & ButtonHTMLAttributes<HTMLButtonElement>

export function PostIt({
  children,
  tone = 'yellow',
  marker,
  selected = false,
  placeholder = false,
  className,
  type = 'button',
  ...rest
}: PostItProps) {
  const classes = [
    'postIt',
    tone,
    selected && 'selected',
    placeholder && 'placeholder',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button type={type} className={classes} aria-pressed={selected} {...rest}>
      {marker ? <span className="marker">{marker}</span> : null}
      {placeholder && !children ? (
        <span className="lines" aria-hidden="true" />
      ) : (
        <span className="body">{children}</span>
      )}
    </button>
  )
}
