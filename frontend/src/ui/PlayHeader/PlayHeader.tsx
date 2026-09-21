import { useNavigate } from 'react-router-dom'
import type { PuzzleMode } from '@/api/types'
import { InkButton } from '@/ui/InkButton/InkButton'
import './PlayHeader.scss'

const MODE_LABEL: Record<PuzzleMode, string> = {
  easy: 'Easy',
  hard: 'Hard',
  medium: 'Medium',
}

type PlayHeaderProps = {
  mode: PuzzleMode
  streak: number
}

export function PlayHeader({ mode, streak }: PlayHeaderProps) {
  const navigate = useNavigate()

  return (
    <header className="playHeader">
      <InkButton onClick={() => navigate('/')}>
        ← Home
      </InkButton>
      <p className="brand">EtymoloGuessr</p>
      <p className="mode" aria-live="polite">
        <span className="modeLabel">{MODE_LABEL[mode]}</span>
        <div className="streak">{`|Streak: ${streak}`}</div>
      </p>
    </header>
  )
}
