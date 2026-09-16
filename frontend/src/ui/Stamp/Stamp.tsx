import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { useId } from 'react'
import './Stamp.scss'

type HintPlacement = 'bottom' | 'left'

type StampProps = {
  children: ReactNode
  size?: 'md' | 'lg'
  hint?: string
  hintPlacement?: HintPlacement
  className?: string
} & ButtonHTMLAttributes<HTMLButtonElement>

export function Stamp({
  children,
  size = 'md',
  hint,
  hintPlacement = 'bottom',
  className,
  type = 'button',
  ...rest
}: StampProps) {
  const hintId = useId()
  const classes = ['stamp', size, className].filter(Boolean).join(' ')

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
    <span className={`stampWithHint ${hintPlacement}`}>
      {button}
      <span id={hintId} role="tooltip" className="hint">
        {hint}
      </span>
    </span>
  )
}
