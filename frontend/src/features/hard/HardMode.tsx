import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  clearHardPuzzleLock,
  fetchLockedRandomHard,
  isPuzzleNotFound,
  puzzleKeys,
  solveHardPuzzle,
} from '@/api/puzzles'
import type { GraphEdge, PuzzlePrompt } from '@/api/types'
import { Colophon, PlayHeader, Sheet, Stamp } from '@/ui'
import { useStreak } from '@/utils/streak'
import { FeedbackScreen } from '../feedback/FeedbackScreen'
import { HardCanvas, type HardCanvasHandle } from './HardCanvas'
import './HardMode.scss'

const randomHardQuery = {
  queryKey: puzzleKeys.randomHard,
  queryFn: fetchLockedRandomHard,
  staleTime: Infinity,
  gcTime: Infinity,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  refetchOnMount: false,
} as const

export function HardMode() {
  const queryClient = useQueryClient()
  const canvasRef = useRef<HardCanvasHandle>(null)
  const [gradedPuzzle, setGradedPuzzle] = useState<PuzzlePrompt>()
  const [allPlaced, setAllPlaced] = useState(false)
  const { streak, recordResult } = useStreak('hard')

  const solveMutation = useMutation({
    mutationFn: ({ id, edges }: { id: string; edges: GraphEdge[] }) => solveHardPuzzle(id, edges),
    onSuccess: (result) => {
      recordResult(result.correct)
      clearHardPuzzleLock()
      queryClient.removeQueries({ queryKey: puzzleKeys.randomHard })
    },
    onError: (error) => {
      if (!isPuzzleNotFound(error)) {
        return
      }
      setGradedPuzzle(undefined)
      queryClient.removeQueries({ queryKey: puzzleKeys.randomHard })
    },
  })
  const solved = solveMutation.isSuccess
  const revealing = solveMutation.isPending || solved

  const puzzleQuery = useQuery({
    ...randomHardQuery,
    enabled: !solved,
  })

  const puzzle = puzzleQuery.data ?? gradedPuzzle
  const graph = puzzle?.promptGraph
  const loading = !puzzle && puzzleQuery.isPending
  const loadError = !puzzle && puzzleQuery.isError
  const missingGraph = Boolean(puzzle && !graph)

  const stampHint = loadError
    ? (puzzleQuery.error instanceof Error
      ? puzzleQuery.error.message
      : 'Could not load a puzzle.')
    : missingGraph
      ? 'This puzzle has no graph to place.'
      : solveMutation.isError
        ? (solveMutation.error instanceof Error
          ? solveMutation.error.message
          : 'Could not submit that graph.')
        : allPlaced
          ? 'Submit when ready.'
          : 'Build the graph!'

  function handleNext() {
    setGradedPuzzle(undefined)
    setAllPlaced(false)
    solveMutation.reset()
  }

  return (
    <Sheet as="main" tone="paper" className="hardMode">
      <PlayHeader mode="hard" streak={streak} />

      {revealing ? null : (
        <p className="instruction">
          Place every card on the blotter, then draw lines from descendant to ancestor.
        </p>
      )}

      {revealing ? (
        <FeedbackScreen
          result={solveMutation.data}
          leafA={puzzle?.leafA}
          leafB={puzzle?.leafB}
          onNext={handleNext}
        />
      ) : (
        <>
          {loading ? (
            <div className="graphPlaceholder" aria-busy="true" />
          ) : graph ? (
            <HardCanvas
              ref={canvasRef}
              key={puzzle?.id}
              graph={graph}
              leafA={puzzle?.leafA}
              leafB={puzzle?.leafB}
              disabled={solveMutation.isPending}
              onAllPlacedChange={setAllPlaced}
            />
          ) : null}

          <section className="submit" aria-label="Submit area">
            {loadError || missingGraph ? (
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
                disabled={!puzzle || !graph || !allPlaced || solveMutation.isPending}
                aria-label="Submit graph"
                onClick={() => {
                  if (!puzzle) {
                    return
                  }
                  setGradedPuzzle(puzzle)
                  solveMutation.mutate({
                    id: puzzle.id,
                    edges: canvasRef.current?.getGraphEdges() ?? [],
                  })
                }}
              >
                Submit
              </Stamp>
            )}
          </section>
        </>
      )}

      <Colophon />
    </Sheet>
  )
}
