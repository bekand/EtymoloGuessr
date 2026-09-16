import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './InkButton.scss'

type InkButtonProps = {
  children: ReactNode
  variant?: 'ink' | 'ghost'
  className?: string
} & ButtonHTMLAttributes<HTMLButtonElement>

export function InkButton({
  children,
  variant = 'ink',
  className,
  type = 'button',
  ...rest
}: InkButtonProps) {
  const classes = ['inkButton', variant, className].filter(Boolean).join(' ')

  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  )
}
