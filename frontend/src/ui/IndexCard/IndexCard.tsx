import type { ReactNode } from 'react'
import './IndexCard.scss'

type IndexCardProps = {
  term?: string
  lang?: string
  gloss?: string
  placeholder?: boolean
  children?: ReactNode
  className?: string
}

export function IndexCard({
  term,
  lang,
  gloss,
  placeholder = false,
  children,
  className,
}: IndexCardProps) {
  const classes = ['indexCard', placeholder && 'placeholder', className].filter(Boolean).join(' ')

  return (
    <article className={classes} aria-label={placeholder ? 'Word card placeholder' : term}>
      {lang ? <span className="lang">{lang}</span> : null}
      {term ? <h3 className="term">{term}</h3> : null}
      {gloss ? <p className="gloss">{gloss}</p> : null}
      {placeholder && !term ? (
        <div className="empty">
          <span className="emptyRule" />
          <span className="emptyRule" />
        </div>
      ) : null}
      {children}
    </article>
  )
}
