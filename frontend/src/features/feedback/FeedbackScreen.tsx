import type { Graph, PuzzleMode, Term } from '@/api/types'
import { EtymologyGraph, Stamp } from '@/ui'
import { joinClasses } from '@/utils/joinClasses'
import './FeedbackScreen.scss'

export type FeedbackResult = {
  correct: boolean
  goldGraph: Graph
}

type FeedbackScreenProps = {
  mode: PuzzleMode
  result?: FeedbackResult
  leafA?: Term
  leafB?: Term
  onNext: () => void
}

export function FeedbackScreen({ mode, result, leafA, leafB, onNext }: FeedbackScreenProps) {
  const solved = Boolean(result)

  return (
    <section className="feedbackScreen" aria-live="polite">
      {solved ? (
        <p className={joinClasses('verdict', result?.correct ? 'ok' : 'no')}>
          {result?.correct ? 'Correct! ' : "Unfortunately, that's not correct..."}
        </p>
      ) : (
        <p className="verdict pending">Checking the archive…</p>
      )}
      {result?.goldGraph ? (
        <EtymologyGraph graph={result.goldGraph} leafA={leafA} leafB={leafB} />
      ) : (
        <div className="graphPlaceholder" aria-busy="true" />
      )}
      {solved ? (
        <div className="nextRow">
          <Stamp
            tone={mode === 'hard' ? 'red' : 'green'}
            onClick={onNext}
            aria-label="Load the next puzzle"
          >
            Next
          </Stamp>
        </div>
      ) : null}
    </section>
  )
}
