import { Colophon, InkButton, Sheet, Stamp } from '@/ui'
import styles from './HomeScreen.module.css'

type HomeScreenProps = {
  onEasy: () => void
  onHard: () => void
}

export function HomeScreen({ onEasy, onHard }: HomeScreenProps) {
  return (
    <Sheet as="main" tone="paper" className={styles.home}>
      <div className={styles.atmosphere} aria-hidden="true" />
      <div className={styles.content}>
        <p className={styles.brand}>EtymoGuessr</p>
        <h1 className={styles.headline}>Trace two words to one ancestor.</h1>
        <p className={styles.lede}>
          A paper desk for etymology puzzles — choose a mode to begin.
        </p>
        <div className={styles.actions}>
          <Stamp size="lg" onClick={onEasy} aria-label="Play Easy mode">
            Easy
          </Stamp>
          <Stamp size="lg" onClick={onHard} aria-label="Open Hard mode">
            Hard
          </Stamp>
        </div>
        <p className={styles.note}>
          Puzzle data arrives with the Go API — shells only for now.
        </p>
        <InkButton variant="ghost" className={styles.ghostHint} disabled>
          Waiting on API
        </InkButton>
      </div>
      <Colophon className={styles.colophon} />
    </Sheet>
  )
}
