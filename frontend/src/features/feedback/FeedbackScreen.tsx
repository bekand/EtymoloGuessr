import type { Graph, MediumPairOrigin, PuzzleMode, Term } from '@/api/types'
import type { StampTone } from '@/ui/Stamp/Stamp'
import { EtymologyGraph, Stamp } from '@/ui'
import { joinClasses } from '@/utils/joinClasses'
import './FeedbackScreen.scss'

export type FeedbackResult = {
  correct: boolean
  goldGraph?: Graph
  ancestors?: Term[]
  pairOrigins?: MediumPairOrigin[]
}

type FeedbackScreenProps = {
  mode: PuzzleMode
  result?: FeedbackResult
  leafA?: Term
  leafB?: Term
  onNext: () => void
}

const NEXT_TONE: Record<PuzzleMode, StampTone> = {
  easy: 'green',
  hard: 'red',
  medium: 'blue',
}

export function FeedbackScreen({ mode, result, leafA, leafB, onNext }: FeedbackScreenProps) {
  const solved = Boolean(result)
  const showAncestors = mode === 'medium'
  const ready = showAncestors
    ? Boolean(result?.ancestors && result.ancestors.length > 0)
    : Boolean(result?.goldGraph)

  return (
    <section className="feedbackScreen" aria-live="polite">
      {solved ? (
        <p className={joinClasses('verdict', result?.correct ? 'ok' : 'no')}>
          {result?.correct ? 'Correct! ' : "Unfortunately, that's not correct..."}
        </p>
      ) : (
        <p className="verdict pending" aria-live="polite">
          Checking the archive…
        </p>
      )}
      {ready ? (
        showAncestors ? (
          <ul className="ancestorGrid" aria-label="Shared ancestors">
            {result?.pairOrigins?.length
              ? result.pairOrigins.map((origin, index) => (
                  <li key={`${origin.ancestor.lang}:${origin.ancestor.term}`} className="ancestorTile">
                    <div className="originPair">
                      <span className="originLabel">Pair {String.fromCharCode(65 + index)}</span>
                      <span className="originWords">
                        {origin.pair[0].term} <span aria-hidden="true">+</span> {origin.pair[1].term}
                      </span>
                    </div>
                    <div className="ancestorMeaning">
                      <span className="ancestorLang">{origin.ancestor.lang}</span>
                      <span className="ancestorTerm">{origin.ancestor.term}</span>
                      {origin.ancestor.gloss ? (
                        <span className="ancestorGloss">{origin.ancestor.gloss}</span>
                      ) : null}
                    </div>
                  </li>
                ))
              : (result?.ancestors ?? []).map((ancestor) => (
                  <li key={`${ancestor.lang}:${ancestor.term}`} className="ancestorTile">
                    <span className="ancestorLang">{ancestor.lang}</span>
                    <span className="ancestorTerm">{ancestor.term}</span>
                    {ancestor.gloss ? <span className="ancestorGloss">{ancestor.gloss}</span> : null}
                  </li>
                ))}
          </ul>
        ) : result?.goldGraph ? (
          <EtymologyGraph graph={result.goldGraph} leafA={leafA} leafB={leafB} />
        ) : null
      ) : (
        <div
          className={showAncestors ? 'ancestorPlaceholder' : 'graphPlaceholder'}
          aria-busy="true"
        />
      )}
      {solved ? (
        <div className="nextRow">
          <Stamp tone={NEXT_TONE[mode]} onClick={onNext} aria-label="Load the next puzzle">
            Next
          </Stamp>
        </div>
      ) : null}
    </section>
  )
}
