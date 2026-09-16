import type { ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './InkButton.module.css'

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
  const classes = [styles.button, styles[variant], className].filter(Boolean).join(' ')

  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  )
}
