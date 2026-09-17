import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './InkButton.scss'

type InkButtonProps = {
  children: ReactNode
  className?: string
} & ButtonHTMLAttributes<HTMLButtonElement>

export function InkButton({
  children,
  className,
  type = 'button',
  ...rest
}: InkButtonProps) {
  const classes = ['inkButton', className].filter(Boolean).join(' ')

  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  )
}
