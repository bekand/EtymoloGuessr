import { useNavigate } from 'react-router-dom'
import { Colophon, Sheet, Stamp } from '@/ui'
import './HomeScreen.scss'

export function HomeScreen() {
  const navigate = useNavigate()

  return (
    <main className="homeScreen">
      <div className="atmosphere" aria-hidden="true" />
      <Sheet as="section" tone="paper">
        <p className="pageLabel">Home</p>
        <p className="brand">EtymoGuessr</p>
        <h1 className="headline">Trace two words to one ancestor.</h1>
        <div className="actions">
          <Stamp size="lg" onClick={() => navigate('/easy')} aria-label="Play Easy mode">
            Easy
          </Stamp>
          <Stamp size="lg" onClick={() => navigate('/hard')} aria-label="Play Hard mode">
            Hard
          </Stamp>
        </div>
        <p className="note">
          Easy: pick the shared ancestor meaning. <br /> Hard: place every word and draw the family tree.
        </p>
      </Sheet>
      <Colophon />
    </main>
  )
}
