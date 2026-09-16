import './Colophon.scss'

type ColophonProps = {
  className?: string
}

export function Colophon({ className }: ColophonProps) {
  const classes = ['colophon', className].filter(Boolean).join(' ')

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
        </a>
        .
      </p>
      <p className="line">
        Licensed under{' '}
        <a
          href="https://creativecommons.org/licenses/by-sa/3.0/"
          target="_blank"
          rel="noreferrer noopener"
        >
          CC BY-SA 3.0
        </a>
        . Material has been modified for puzzle generation.
      </p>
    </footer>
  )
}
