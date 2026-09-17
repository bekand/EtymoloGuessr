import { useId, useState, type ReactNode } from 'react'
import { joinClasses } from '@/utils/joinClasses'
import './IndexCard.scss'

type ExplainSide = 'left' | 'right'

type IndexCardProps = {
  term?: string
  lang?: string
  gloss?: string
  explainSide?: ExplainSide
  explainOpen?: boolean
  onExplainOpenChange?: (open: boolean) => void
  placeholder?: boolean
  children?: ReactNode
  className?: string
}

export function IndexCard({
  term,
  lang,
  gloss,
  explainSide = 'right',
  explainOpen,
  onExplainOpenChange,
  placeholder = false,
  children,
  className,
}: IndexCardProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false)
  const meaningId = useId()
  const hasGloss = Boolean(gloss) && !placeholder
  const controlled = explainOpen !== undefined
  const open = hasGloss && (controlled ? explainOpen : uncontrolledOpen)
  const classes = joinClasses('indexCard', placeholder && 'placeholder', className)
  const explainLabel = explainSide === 'left' ? '< Explain' : 'Explain >'

  function toggleExplain() {
    const next = !open
    if (!controlled) {
      setUncontrolledOpen(next)
    }
    onExplainOpenChange?.(next)
  }

  const card = (
    <article className={classes} aria-label={placeholder ? 'Word card placeholder' : term}>
      {lang ? <span className="lang">{lang}</span> : null}
      {term ? <h3 className="term">{term}</h3> : null}
      {placeholder && !term ? (
        <div className="empty">
          <span className="emptyRule" />
        </div>
      ) : null}
      {hasGloss ? (
        <button
          type="button"
          className="explain"
          aria-expanded={open}
          aria-controls={meaningId}
          onClick={toggleExplain}
        >
          {explainLabel}
        </button>
      ) : null}
      {children}
    </article>
  )

  const meaning = hasGloss ? (
    <div id={meaningId} className={joinClasses('meaning', open && 'open')} aria-hidden={!open}>
      <p className="meaningText">{gloss}</p>
    </div>
  ) : null

  return (
    <div className={`indexCardUnit ${explainSide}`}>
      {explainSide === 'left' ? meaning : null}
      {card}
      {explainSide === 'right' ? meaning : null}
    </div>
  )
}
