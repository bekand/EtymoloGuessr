import { useRef, useState } from 'react'
import { solveHardPuzzle } from '@/api/puzzles'
import type { GraphEdge } from '@/api/types'
import { Colophon, PlayHeader, Sheet, Stamp } from '@/ui'
import { joinClasses } from '@/utils/joinClasses'
import { useSettlingClip } from '@/utils/useSettlingClip'
import { FeedbackScreen } from '../feedback/FeedbackScreen'
import { useSolvePuzzle } from '../hooks/useSolvePuzzle'
import { HardCanvas, type HardCanvasHandle } from './HardCanvas'
import './HardMode.scss'

export function HardMode() {
  const canvasRef = useRef<HardCanvasHandle>(null)
  const [allPlaced, setAllPlaced] = useState(false)
  const [placedCount, setPlacedCount] = useState(0)
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
    'hard',
    ({ id, edges }: { id: string; edges: GraphEdge[] }) => solveHardPuzzle(id, edges),
  )

  const graph = puzzle?.promptGraph
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
    setAllPlaced(false)
    setPlacedCount(0)
    next()
  }

  const progressText = graph
    ? allPlaced
      ? 'All cards placed'
      : `${placedCount}/${graph.nodes.length} cards placed`
    : 'Waiting for cards'

  return (
    <Sheet
      as="main"
      tone="kraft"
      className={joinClasses('hardMode', settling && 'settling')}
      onAnimationEnd={onAnimationEnd}
    >
      <PlayHeader mode="hard" streak={streak} />

      {revealing ? null : (
        <>
          <p className="instruction">
            Place every card on the blotter, then draw lines from descendant to ancestor.
          </p>
          <p className="statusLine" aria-live="polite">{progressText}</p>
        </>
      )}

      {revealing ? (
        <FeedbackScreen
          mode="hard"
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
              onPlacedCountChange={setPlacedCount}
            />
          ) : null}

          <section className="submit" aria-label="Submit area">
            {loadError || missingGraph ? (
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
                tone="red"
                hint={stampHint}
                disabled={!puzzle || !graph || !allPlaced || solveMutation.isPending}
                aria-label="Submit graph"
                onClick={() => {
                  if (!puzzle) {
                    return
                  }
                  submit(puzzle, {
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
