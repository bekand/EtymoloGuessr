import { useNavigate } from 'react-router-dom'
import type { PuzzleMode } from '@/api/types'
import { InkButton } from '@/ui/InkButton/InkButton'
import './PlayHeader.scss'

const MODE_LABEL: Record<PuzzleMode, string> = {
  easy: 'Easy',
  hard: 'Hard',
}

type PlayHeaderProps = {
  mode: PuzzleMode
  streak: number
}

export function PlayHeader({ mode, streak }: PlayHeaderProps) {
  const navigate = useNavigate()

  return (
    <header className="playHeader">
      <InkButton variant="ghost" onClick={() => navigate('/')}>
        ← Home
      </InkButton>
      <p className="brand">EtymoGuessr</p>
      <p className="mode" aria-live="polite">
        {`${MODE_LABEL[mode]}   [ Streak ${streak} ]`}
      </p>
    </header>
  )
}
