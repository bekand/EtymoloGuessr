import { Colophon, Sheet, Stamp } from '@/ui'
import './HomeScreen.scss'

type HomeScreenProps = {
  onEasy: () => void
}

export function HomeScreen({ onEasy }: HomeScreenProps) {
  return (
    <main className="homeScreen">
      <div className="atmosphere" aria-hidden="true" />
      <Sheet as="section" tone="paper">
        <p className="pageLabel">Home</p>
        <p className="brand">EtymoGuessr</p>
        <h1 className="headline">Trace two words to one ancestor.</h1>
        <div className="actions">
          <Stamp size="lg" onClick={onEasy} aria-label="Play Easy mode">
            Easy
          </Stamp>
          <Stamp size="lg" disabled aria-label="Hard mode coming soon">
            Hard
          </Stamp>
        </div>
        <p className="note">
          Puzzle data arrives with the Go API — shells only for now.
        </p>
      </Sheet>
      <Colophon />
    </main>
  )
}
