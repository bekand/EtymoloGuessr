import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './Stamp.scss'

type StampProps = {
  children: ReactNode
  size?: 'md' | 'lg'
  className?: string
} & ButtonHTMLAttributes<HTMLButtonElement>

export function Stamp({
  children,
  size = 'md',
  className,
  type = 'button',
  ...rest
}: StampProps) {
  const classes = ['stamp', size, className].filter(Boolean).join(' ')

  return (
    <button type={type} className={classes} {...rest}>
      <span className="plate">
        <span className="label">{children}</span>
      </span>
    </button>
  )
}
