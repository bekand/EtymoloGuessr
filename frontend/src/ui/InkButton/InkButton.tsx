import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { joinClasses } from '@/utils/joinClasses'
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
  const classes = joinClasses('inkButton', className)

  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  )
}
