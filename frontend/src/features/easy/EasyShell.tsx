import { Colophon, IndexCard, InkButton, PostIt, Sheet, Stamp } from '@/ui'
import './EasyShell.scss'

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
    <Sheet as="main" tone="paper" className="easyShell">
      <header className="header">
        <InkButton variant="ghost" onClick={onBack}>
          ← Home
        </InkButton>
        <p className="brand">EtymoGuessr</p>
        <p className="mode">Easy · shell</p>
      </header>

      <section className="prompt" aria-label="Word pair placeholders">
        <p className="instruction">
          What meaning do these words share in their common ancestor?
        </p>
        <div className="cards">
          <IndexCard placeholder lang="—" />
          <span className="ampersand" aria-hidden="true">
            &amp;
          </span>
          <IndexCard placeholder lang="—" />
        </div>
      </section>

      <div className="playRow">
        <section className="choices" aria-label="Meaning choices placeholders">
          <p className="sectionLabel">Choose one</p>
          <div className="notes">
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

        <section className="submit" aria-label="Submit area">
          <Stamp disabled aria-label="Submit answer (unavailable until API)">
            Submit
          </Stamp>
          <p className="waitNote">
            Layout only — puzzle fetch waits on the Go API. No mock data.
          </p>
        </section>
      </div>

      <Colophon />
    </Sheet>
  )
}
