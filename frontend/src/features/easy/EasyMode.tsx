import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  clearEasyPuzzleLock,
  fetchLockedRandomEasy,
  puzzleKeys,
  solveEasyPuzzle,
} from '@/api/puzzles'
import type { PuzzlePrompt } from '@/api/types'
import { Colophon, EtymologyGraph, IndexCard, InkButton, PostIt, Sheet, Stamp } from '@/ui'
import { shuffle } from '@/utils/shuffle'
import './EasyMode.scss'

type EasyModeProps = {
  onBack: () => void
}

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

export function EasyMode({ onBack }: EasyModeProps) {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [gradedPuzzle, setGradedPuzzle] = useState<PuzzlePrompt>()
  const [explainOpen, setExplainOpen] = useState<'left' | 'right' | null>(null)

  const solveMutation = useMutation({
    mutationFn: ({ id, choiceId }: { id: string; choiceId: string }) =>
      solveEasyPuzzle(id, choiceId),
    onSuccess: () => {
      clearEasyPuzzleLock()
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
        ? 'Stamp when you are sure.'
        : 'Pick a meaning, then stamp.'

  function handleNext() {
    setGradedPuzzle(undefined)
    setSelectedId(null)
    setExplainOpen(null)
    solveMutation.reset()
  }

  return (
    <Sheet as="main" tone="paper" className="easyMode">
      <header className="header">
        <InkButton variant="ghost" onClick={onBack}>
          ← Home
        </InkButton>
        <p className="brand">EtymoGuessr</p>
        <p className="mode">Easy</p>
      </header>

      {revealing ? null : (
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
      )}

      {revealing ? (
        <section className="reveal" aria-live="polite">
          {solved ? (
            <p className={`verdict ${solveMutation.data?.correct ? 'ok' : 'no'}`}>
              {solveMutation.data?.correct
                ? 'Correct! '
                : "Unfortunately, that's not correct..."}
            </p>
          ) : (
            <p className="verdict pending">Checking the archive…</p>
          )}
          {solveMutation.data?.goldGraph ? (
            <EtymologyGraph
              graph={solveMutation.data.goldGraph}
              leafA={puzzle?.leafA}
              leafB={puzzle?.leafB}
            />
          ) : (
            <div className="graphPlaceholder" aria-busy="true" />
          )}
          {solved ? (
            <div className="nextRow">
              <Stamp onClick={handleNext} aria-label="Load the next puzzle">
                Next
              </Stamp>
            </div>
          ) : null}
        </section>
      ) : (
        <div className="playRow">
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

          <section className="submit" aria-label="Submit area">
            {loadError ? (
              <Stamp
                hint={stampHint}
                hintPlacement="right"
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
                hintPlacement="right"
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
        </div>
      )}

      <Colophon />
    </Sheet>
  )
}
