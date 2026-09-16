import type { ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './Stamp.module.css'

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
  const classes = [styles.stamp, styles[size], className].filter(Boolean).join(' ')

  return (
    <button type={type} className={classes} {...rest}>
      <span className={styles.plate}>
        <span className={styles.label}>{children}</span>
      </span>
    </button>
  )
}
