import { useRef, useState } from 'react'
import { solveHardPuzzle } from '@/api/puzzles'
import type { GraphEdge } from '@/api/types'
import { Stamp } from '@/ui'
import { useSettlingClip } from '@/utils/useSettlingClip'
import { FeedbackScreen } from '../feedback/FeedbackScreen'
import { useSolvePuzzle } from '../hooks/useSolvePuzzle'
import { ModeShell } from '../modes/ModeShell'
import { getStampHint } from '../modes/stampHint'
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

  const stampHint = getStampHint(
    {
      loadError: loadError ? puzzleQuery.error ?? true : null,
      submitError: solveMutation.isError ? solveMutation.error ?? true : null,
      ready: allPlaced,
    },
    {
      onError: 'Could not load a puzzle.',
      onReady: missingGraph ? 'This puzzle has no graph to place.' : 'Build the graph!',
      onSubmitError: 'Could not submit that graph.',
      onSubmitReady: 'Submit when ready.',
    },
  )

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
    <ModeShell
      mode="hard"
      streak={streak}
      settling={settling}
      onAnimationEnd={onAnimationEnd}
      instruction={revealing ? undefined : 'Place every card on the blotter, then draw lines from descendant to ancestor.'}
    >
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
          <p className="statusLine" aria-live="polite">{progressText}</p>
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

    </ModeShell>
  )
}
