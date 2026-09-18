import type { ButtonHTMLAttributes, PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import { useId, useRef } from 'react'
import { joinClasses } from '@/utils/joinClasses'
import './Stamp.scss'

const TOUCH_ACTIVATION_DELAY_MS = 160

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
  onClick,
  onPointerCancel,
  onPointerUp,
  ...rest
}: StampProps) {
  const hintId = useId()
  const touchActivationTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const touchActivationPending = useRef(false)
  const classes = joinClasses('stamp', size, tone, className)

  const clearTouchActivation = () => {
    if (touchActivationTimer.current !== null) {
      clearTimeout(touchActivationTimer.current)
      touchActivationTimer.current = null
    }
    touchActivationPending.current = false
  }

  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (touchActivationPending.current) {
      event.preventDefault()
      return
    }
    onClick?.(event)
  }

  const handlePointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    onPointerUp?.(event)

    if (event.pointerType !== 'touch' || !onClick) {
      return
    }

    touchActivationPending.current = true
    touchActivationTimer.current = setTimeout(() => {
      touchActivationPending.current = false
      touchActivationTimer.current = null
      onClick(event as unknown as React.MouseEvent<HTMLButtonElement>)
    }, TOUCH_ACTIVATION_DELAY_MS)
  }

  const handlePointerCancel = (event: ReactPointerEvent<HTMLButtonElement>) => {
    clearTouchActivation()
    onPointerCancel?.(event)
  }

  const button = (
    <button
      type={type}
      className={classes}
      aria-describedby={hint ? hintId : undefined}
      onClick={handleClick}
      onPointerCancel={handlePointerCancel}
      onPointerUp={handlePointerUp}
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
