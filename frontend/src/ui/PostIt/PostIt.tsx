import { useState, type ButtonHTMLAttributes, type CSSProperties, type ReactNode } from 'react'
import './PostIt.scss'

export const POST_IT_MIN_TILT_DEG = 0.2
export const POST_IT_MAX_TILT_DEG = 1

function randomTiltDeg() {
  const unit = Math.random()
  const towardMax = unit < 0.5 ? unit * 2 : (unit - 0.5) * 2
  const magnitude =
    POST_IT_MIN_TILT_DEG + towardMax * (POST_IT_MAX_TILT_DEG - POST_IT_MIN_TILT_DEG)
  return (unit < 0.5 ? -1 : 1) * magnitude
}

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
  style,
  ...rest
}: PostItProps) {
  const [tilt] = useState(randomTiltDeg)
  const classes = [
    'postIt',
    tone,
    selected && 'selected',
    placeholder && 'placeholder',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  const tiltStyle = {
    ...style,
    '--post-it-tilt': `${tilt}deg`,
  } as CSSProperties

  return (
    <button type={type} className={classes} aria-pressed={selected} {...rest} style={tiltStyle}>
      {marker ? <span className="marker">{marker}</span> : null}
      {placeholder && !children ? (
        <span className="lines" aria-hidden="true" />
      ) : (
        <span className="body">{children}</span>
      )}
    </button>
  )
}
