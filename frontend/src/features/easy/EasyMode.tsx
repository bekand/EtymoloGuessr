import { useState } from 'react'
import { solveEasyPuzzle } from '@/api/puzzles'
import { IndexCard, PostIt, Stamp } from '@/ui'
import { shuffle } from '@/utils/shuffle'
import { useSettlingClip } from '@/utils/useSettlingClip'
import { FeedbackScreen } from '../feedback/FeedbackScreen'
import { useSolvePuzzle } from '../hooks/useSolvePuzzle'
import { ModeShell } from '../modes/ModeShell'
import { getStampHint } from '../modes/stampHint'
import './EasyMode.scss'

const CHOICE_TONES = ['yellow', 'pink', 'blue', 'green'] as const
const CHOICE_MARKERS = ['A', 'B', 'C', 'D'] as const

export function EasyMode() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [explainOpen, setExplainOpen] = useState<'left' | 'right' | null>(null)
  const { settling, onAnimationEnd } = useSettlingClip()
  const {
    puzzle,
    puzzleQuery,
    solveMutation,
    revealing,
    loading,
    loadError,
    streak,
    submit,
    next,
  } = useSolvePuzzle(
    'easy',
    ({ id, choiceId }: { id: string; choiceId: string }) => solveEasyPuzzle(id, choiceId),
    () => setSelectedId(null),
  )

  const shuffleSeed = puzzle?.id ?? 'loading'
  const choiceTones = shuffle(CHOICE_TONES, shuffleSeed)
  const choices = shuffle(puzzle?.choices ?? [null, null, null, null], shuffleSeed)

  const stampHint = getStampHint(
    {
      loadError: loadError ? puzzleQuery.error ?? true : null,
      submitError: solveMutation.isError ? solveMutation.error ?? true : null,
      ready: Boolean(selectedId),
    },
    {
      onError: 'Could not load a puzzle.',
      onReady: 'Pick an answer!',
      onSubmitError: 'Could not submit that answer.',
      onSubmitReady: 'Submit when you are sure.',
    },
  )

  const progressText = selectedId ? 'Choice selected' : 'Choose one'

  function handleNext() {
    setSelectedId(null)
    setExplainOpen(null)
    next()
  }

  function renderPrompt() {
    return (
      <section className="prompt" aria-label="Word pair">
        <p className="instruction">
          What meaning do these words share in their common ancestor?
        </p>
        <div className="cards">
          <IndexCard
            key={`${puzzle?.id ?? 'loading'}-a`}
            placeholder={loading}
            lang={puzzle?.leafA.lang ?? '—'}
            term={puzzle?.leafA.term}
            gloss={puzzle?.leafA.gloss ?? undefined}
            explainSide="left"
            explainOpen={explainOpen === 'left'}
            onExplainOpenChange={(open) => setExplainOpen(open ? 'left' : null)}
          />
          <span className="ampersand" aria-hidden="true">
            &amp;
          </span>
          <IndexCard
            key={`${puzzle?.id ?? 'loading'}-b`}
            placeholder={loading}
            lang={puzzle?.leafB.lang ?? '—'}
            term={puzzle?.leafB.term}
            gloss={puzzle?.leafB.gloss ?? undefined}
            explainSide="right"
            explainOpen={explainOpen === 'right'}
            onExplainOpenChange={(open) => setExplainOpen(open ? 'right' : null)}
          />
        </div>
      </section>
    )
  }

  function renderChoices() {
    return (
      <section className="choices" aria-label="Meaning choices">
        <p className="sectionLabel">{progressText}</p>
        <div className="notes">
          {choices.map((choice, index) => {
            const marker = CHOICE_MARKERS[index] ?? String(index + 1)
            const tone = choiceTones[index % choiceTones.length]
            return (
              <PostIt
                key={choice?.id ?? marker}
                tone={tone}
                marker={marker}
                placeholder={!choice}
                disabled={!choice}
                selected={Boolean(choice && selectedId === choice.id)}
                aria-label={choice ? `Choice ${marker}: ${choice.gloss}` : `Choice ${marker}`}
                onClick={() => {
                  if (choice) {
                    setSelectedId(choice.id)
                  }
                }}
              >
                {choice?.gloss}
              </PostIt>
            )
          })}
        </div>
      </section>
    )
  }

  function renderSubmit() {
    return (
      <section className="submit" aria-label="Submit area">
        {loadError ? (
          <Stamp
            hint={stampHint}
            onClick={() => {
              void puzzleQuery.refetch()
            }}
            aria-label="Retry loading a puzzle"
          >
            Retry
          </Stamp>
        ) : (
          <Stamp
            tone="green"
            hint={stampHint}
            disabled={!puzzle || !selectedId || solveMutation.isPending}
            aria-label="Submit answer"
            onClick={() => {
              if (!puzzle || !selectedId) {
                return
              }
              setExplainOpen(null)
              submit(puzzle, { id: puzzle.id, choiceId: selectedId })
            }}
          >
            Submit
          </Stamp>
        )}
      </section>
    )
  }

  return (
    <ModeShell mode="easy" streak={streak} settling={settling} onAnimationEnd={onAnimationEnd}>
      {revealing ? null : renderPrompt()}

      {revealing ? (
        <FeedbackScreen
          mode="easy"
          result={solveMutation.data}
          leafA={puzzle?.leafA}
          leafB={puzzle?.leafB}
          onNext={handleNext}
        />
      ) : (
        <div className="playRow">
          {renderChoices()}
          {renderSubmit()}
        </div>
      )}

    </ModeShell>
  )
}
