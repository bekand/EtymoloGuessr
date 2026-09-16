import { Colophon, Sheet, Stamp } from '@/ui'
import styles from './HomeScreen.module.css'

type HomeScreenProps = {
  onEasy: () => void
}

export function HomeScreen({ onEasy }: HomeScreenProps) {
  return (
    <main className={styles.home}>
      <div className={styles.atmosphere} aria-hidden="true" />
      <Sheet as="section" tone="paper" className={styles.paper}>
        <p className={styles.pageLabel}>Home</p>
        <p className={styles.brand}>EtymoGuessr</p>
        <h1 className={styles.headline}>Trace two words to one ancestor.</h1>
        <div className={styles.actions}>
          <Stamp size="lg" onClick={onEasy} aria-label="Play Easy mode">
            Easy
          </Stamp>
          <Stamp size="lg" disabled aria-label="Hard mode coming soon">
            Hard
          </Stamp>
        </div>
        <p className={styles.note}>
          Puzzle data arrives with the Go API — shells only for now.
        </p>
      </Sheet>
      <Colophon className={styles.colophon} />
    </main>
  )
}
