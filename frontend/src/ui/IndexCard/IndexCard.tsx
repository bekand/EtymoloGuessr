import type { ReactNode } from 'react'
import styles from './IndexCard.module.css'

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
  const classes = [styles.card, placeholder ? styles.placeholder : '', className]
    .filter(Boolean)
    .join(' ')

  return (
    <article className={classes} aria-label={placeholder ? 'Word card placeholder' : term}>
      {lang ? <span className={styles.lang}>{lang}</span> : null}
      {term ? <h3 className={styles.term}>{term}</h3> : null}
      {gloss ? <p className={styles.gloss}>{gloss}</p> : null}
      {placeholder && !term ? (
        <div className={styles.empty}>
          <span className={styles.emptyRule} />
          <span className={styles.emptyRule} />
        </div>
      ) : null}
      {children}
    </article>
  )
}
