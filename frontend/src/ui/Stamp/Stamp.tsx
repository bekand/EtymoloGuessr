import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { useId } from 'react'
import { joinClasses } from '@/utils/joinClasses'
import './Stamp.scss'

export type StampTone = 'black' | 'red' | 'green' | 'blue'

type StampProps = {
  children: ReactNode
  size?: 'md' | 'lg'
  tone?: StampTone
  hint?: string
  className?: string
} & ButtonHTMLAttributes<HTMLButtonElement>

export function Stamp({
  children,
  size = 'md',
  tone = 'black',
  hint,
  className,
  type = 'button',
  ...rest
}: StampProps) {
  const hintId = useId()
  const classes = joinClasses('stamp', size, tone, className)

  const button = (
    <button
      type={type}
      className={classes}
      aria-describedby={hint ? hintId : undefined}
      {...rest}
    >
      <span className="plate">
        <span className="label">{children}</span>
      </span>
    </button>
  )

  if (!hint) {
    return button
  }

  return (
    <span className="stampWithHint">
      {button}
      <span id={hintId} role="tooltip" className="hint">
        {hint}
      </span>
    </span>
  )
}
