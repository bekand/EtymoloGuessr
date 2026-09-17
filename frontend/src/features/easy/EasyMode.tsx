import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  clearEasyPuzzleLock,
  fetchLockedRandomEasy,
  isPuzzleNotFound,
  puzzleKeys,
  solveEasyPuzzle,
} from '@/api/puzzles'
import type { PuzzlePrompt } from '@/api/types'
import { Colophon, IndexCard, PlayHeader, PostIt, Sheet, Stamp } from '@/ui'
import { shuffle } from '@/utils/shuffle'
import { useStreak } from '@/utils/streak'
import { FeedbackScreen } from '../feedback/FeedbackScreen'
import './EasyMode.scss'

const CHOICE_TONES = ['yellow', 'pink', 'blue', 'green'] as const
const CHOICE_MARKERS = ['A', 'B', 'C', 'D'] as const

const randomEasyQuery = {
  queryKey: puzzleKeys.randomEasy,
  queryFn: fetchLockedRandomEasy,
  staleTime: Infinity,
  gcTime: Infinity,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  refetchOnMount: false,
} as const

export function EasyMode() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [gradedPuzzle, setGradedPuzzle] = useState<PuzzlePrompt>()
  const [explainOpen, setExplainOpen] = useState<'left' | 'right' | null>(null)
  const { streak, recordResult } = useStreak('easy')

  const solveMutation = useMutation({
    mutationFn: ({ id, choiceId }: { id: string; choiceId: string }) =>
      solveEasyPuzzle(id, choiceId),
    onSuccess: (result) => {
      recordResult(result.correct)
      clearEasyPuzzleLock()
      queryClient.removeQueries({ queryKey: puzzleKeys.randomEasy })
    },
    onError: (error) => {
      if (!isPuzzleNotFound(error)) {
        return
      }
      setGradedPuzzle(undefined)
      setSelectedId(null)
      queryClient.removeQueries({ queryKey: puzzleKeys.randomEasy })
    },
  })
  const solved = solveMutation.isSuccess
  const revealing = solveMutation.isPending || solved

  const puzzleQuery = useQuery({
    ...randomEasyQuery,
    enabled: !solved,
  })

  const puzzle = puzzleQuery.data ?? gradedPuzzle
  const loading = !puzzle && puzzleQuery.isPending
  const loadError = !puzzle && puzzleQuery.isError
  const shuffleSeed = puzzle?.id ?? 'loading'
  const choiceTones = shuffle(CHOICE_TONES, shuffleSeed)
  const choices = shuffle(puzzle?.choices ?? [null, null, null, null], shuffleSeed)

  const stampHint = loadError
    ? (puzzleQuery.error instanceof Error
      ? puzzleQuery.error.message
      : 'Could not load a puzzle.')
    : solveMutation.isError
      ? (solveMutation.error instanceof Error
        ? solveMutation.error.message
        : 'Could not submit that answer.')
      : selectedId
        ? 'Submit when you are sure.'
        : 'Pick an answer!'

  function handleNext() {
    setGradedPuzzle(undefined)
    setSelectedId(null)
    setExplainOpen(null)
    solveMutation.reset()
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
        <p className="sectionLabel">Choose one</p>
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
            hintPlacement="left"
            onClick={() => {
              void puzzleQuery.refetch()
            }}
            aria-label="Retry loading a puzzle"
          >
            Retry
          </Stamp>
        ) : (
          <Stamp
            hint={stampHint}
            hintPlacement="left"
            disabled={!puzzle || !selectedId || solveMutation.isPending}
            aria-label="Submit answer"
            onClick={() => {
              if (!puzzle || !selectedId) {
                return
              }
              setGradedPuzzle(puzzle)
              setExplainOpen(null)
              solveMutation.mutate({ id: puzzle.id, choiceId: selectedId })
            }}
          >
            Submit
          </Stamp>
        )}
      </section>
    )
  }

  return (
    <Sheet as="main" tone="blotter" className="easyMode">
      <PlayHeader mode="easy" streak={streak} />

      {revealing ? null : renderPrompt()}

      {revealing ? (
        <FeedbackScreen
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

      <Colophon />
    </Sheet>
  )
}
