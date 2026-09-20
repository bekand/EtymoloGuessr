import { joinClasses } from '@/utils/joinClasses'
import './Colophon.scss'

type ColophonProps = {
  className?: string
}

export function Colophon({ className }: ColophonProps) {
  const classes = joinClasses('colophon', className)

  return (
    <footer className={classes}>
      <p className="line">
        Etymology data adapted from{' '}
        <a
          href="https://en.wiktionary.org/"
          target="_blank"
          rel="noreferrer noopener"
        >
          Wiktionary
        </a>{' '}
        via{' '}
        <a
          href="https://github.com/droher/etymology-db"
          target="_blank"
          rel="noreferrer noopener"
        >
          etymology-db
        </a>{' '}
        and{' '}
        <a
          href="https://kaikki.org/"
          target="_blank"
          rel="noreferrer noopener"
        >
          Kaikki
        </a>
        .
      </p>
      <p className="line">
        Licensed under{' '}
        <a
          href="https://creativecommons.org/licenses/by-sa/4.0/"
          target="_blank"
          rel="noreferrer noopener"
        >
          CC BY-SA 4.0
        </a>
        . Material has been modified for puzzle generation. It may contain
        errors, omissions, and/or simplifications.
      </p>
    </footer>
  )
}
