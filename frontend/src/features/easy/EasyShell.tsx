import { Colophon, IndexCard, InkButton, PostIt, Sheet, Stamp } from '@/ui'
import styles from './EasyShell.module.css'

type EasyShellProps = {
  onBack: () => void
}

const CHOICES = [
  { tone: 'yellow', marker: 'A' },
  { tone: 'pink', marker: 'B' },
  { tone: 'blue', marker: 'C' },
  { tone: 'green', marker: 'D' },
] as const

export function EasyShell({ onBack }: EasyShellProps) {
  return (
    <Sheet as="main" tone="paper" className={styles.shell}>
      <header className={styles.header}>
        <InkButton variant="ghost" onClick={onBack}>
          ← Home
        </InkButton>
        <p className={styles.brand}>EtymoGuessr</p>
        <p className={styles.mode}>Easy · shell</p>
      </header>

      <section className={styles.prompt} aria-label="Word pair placeholders">
        <p className={styles.instruction}>
          What meaning do these words share in their common ancestor?
        </p>
        <div className={styles.cards}>
          <IndexCard placeholder lang="—" />
          <span className={styles.ampersand} aria-hidden="true">
            &amp;
          </span>
          <IndexCard placeholder lang="—" />
        </div>
      </section>

      <div className={styles.playRow}>
        <section className={styles.choices} aria-label="Meaning choices placeholders">
          <p className={styles.sectionLabel}>Choose one</p>
          <div className={styles.notes}>
            {CHOICES.map(({ tone, marker }) => (
              <PostIt
                key={marker}
                tone={tone}
                marker={marker}
                placeholder
                disabled
                aria-label={`Choice ${marker}`}
              />
            ))}
          </div>
        </section>

        <section className={styles.submit} aria-label="Submit area">
          <Stamp disabled aria-label="Submit answer (unavailable until API)">
            Submit
          </Stamp>
          <p className={styles.waitNote}>
            Layout only — puzzle fetch waits on the Go API. No mock data.
          </p>
        </section>
      </div>

      <Colophon />
    </Sheet>
  )
}
