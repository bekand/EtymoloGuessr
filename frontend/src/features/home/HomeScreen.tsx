import { useNavigate } from 'react-router-dom'
import { Sheet, Stamp } from '@/ui'
import './HomeScreen.scss'

export function HomeScreen() {
  const navigate = useNavigate()

  return (
    <main className="homeScreen">
      <div className="atmosphere" aria-hidden="true" />
      <Sheet as="section" tone="paper">
        <p className="brand">EtymoloGuessr</p>
        <h1 className="headline">Trace words to their ancestor</h1>
        <div className="actions">
          <Stamp tone="green" onClick={() => navigate('/easy')} aria-label="Play Easy mode">
            Easy
          </Stamp>
          <Stamp
            tone="blue"
            onClick={() => navigate('/medium')}
            aria-label="Play Medium mode"
          >
            Medium
          </Stamp>
          <Stamp tone="red" onClick={() => navigate('/hard')} aria-label="Play Hard mode">
            Hard
          </Stamp>
        </div>
        <ul className="modeSummary" aria-label="How to play">
          <li>
            <strong>Easy</strong> — pick the shared ancestor meaning.
          </li>
          <li>
            <strong>Medium</strong> — pair the words that share an ancestor.
          </li>
          <li>
            <strong>Hard</strong> — place every word and draw the family tree.
          </li>
        </ul>
      </Sheet>
    </main>
  )
}
