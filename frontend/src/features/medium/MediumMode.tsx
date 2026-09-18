import { useMemo, useState } from 'react'
import { solveMediumPuzzle } from '@/api/puzzles'
import type { MediumLeaf } from '@/api/types'
import { PostIt, Stamp } from '@/ui'
import { useSettlingClip } from '@/utils/useSettlingClip'
import { FeedbackScreen } from '../feedback/FeedbackScreen'
import { useSolvePuzzle } from '../hooks/useSolvePuzzle'
import { ModeShell } from '../modes/ModeShell'
import { getStampHint } from '../modes/stampHint'
import './MediumMode.scss'

const PAIR_SLOTS = [
  { marker: 'A?', tone: 'yellow' },
  { marker: 'B?', tone: 'pink' },
  { marker: 'C?', tone: 'blue' },
  { marker: 'D?', tone: 'green' },
] as const

type PairSlot = (typeof PAIR_SLOTS)[number]
type PairTone = PairSlot['tone']

type CompletedPair = {
  slotIndex: number
  left: string
  right: string
}

type NoteState =
  | { kind: 'idle' }
  | { kind: 'pending'; slotIndex: number }
  | { kind: 'paired'; slotIndex: number }

function nextFreeSlot(pairs: CompletedPair[], pendingSlot: number | null): number | null {
  const used = new Set(pairs.map((p) => p.slotIndex))
  if (pendingSlot !== null) {
    used.add(pendingSlot)
  }
  for (let i = 0; i < PAIR_SLOTS.length; i += 1) {
    if (!used.has(i)) {
      return i
    }
  }
  return null
}

function noteStateFor(
  leafId: string,
  pairs: CompletedPair[],
  pendingId: string | null,
  pendingSlot: number | null,
): NoteState {
  if (pendingId === leafId && pendingSlot !== null) {
    return { kind: 'pending', slotIndex: pendingSlot }
  }
  for (const pair of pairs) {
    if (pair.left === leafId || pair.right === leafId) {
      return { kind: 'paired', slotIndex: pair.slotIndex }
    }
  }
  return { kind: 'idle' }
}

export function MediumMode() {
  const [pairs, setPairs] = useState<CompletedPair[]>([])
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [pendingSlot, setPendingSlot] = useState<number | null>(null)
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
    'medium',
    ({ id, pairs: submitted }: { id: string; pairs: [string, string][] }) =>
      solveMediumPuzzle(id, submitted),
    () => {
      setPairs([])
      setPendingId(null)
      setPendingSlot(null)
    },
  )

  const leaves: MediumLeaf[] = useMemo(() => {
    if (puzzle?.leaves) {
      return puzzle.leaves
    }
    return Array.from({ length: 8 }, (_, i) => ({
      id: `placeholder-${i}`,
      lang: '—',
      term: '',
    }))
  }, [puzzle?.leaves])

  const stampHint = getStampHint(
    {
      loadError: loadError ? puzzleQuery.error ?? true : null,
      submitError: solveMutation.isError ? solveMutation.error ?? true : null,
      ready: pairs.length === 4,
    },
    {
      onError: 'Could not load a puzzle.',
      onReady: 'Pair all eight words.',
      onSubmitError: 'Could not submit that answer.',
      onSubmitReady: 'Submit when you are sure.',
    },
  )

  const progressText = `${pairs.length}/4 pairs matched`

  function resetBoard() {
    setPairs([])
    setPendingId(null)
    setPendingSlot(null)
  }

  function handleNext() {
    resetBoard()
    next()
  }

  function handleNoteClick(leafId: string) {
    if (!puzzle || loading) {
      return
    }
    const state = noteStateFor(leafId, pairs, pendingId, pendingSlot)

    if (state.kind === 'paired') {
      setPairs((prev) => prev.filter((p) => p.slotIndex !== state.slotIndex))
      if (pendingId === leafId) {
        setPendingId(null)
        setPendingSlot(null)
      }
      return
    }

    if (state.kind === 'pending') {
      setPendingId(null)
      setPendingSlot(null)
      return
    }

    if (pendingId !== null && pendingSlot !== null) {
      if (pendingId === leafId) {
        setPendingId(null)
        setPendingSlot(null)
        return
      }
      setPairs((prev) => [
        ...prev,
        { slotIndex: pendingSlot, left: pendingId, right: leafId },
      ])
      setPendingId(null)
      setPendingSlot(null)
      return
    }

    const slot = nextFreeSlot(pairs, null)
    if (slot === null) {
      return
    }
    setPendingId(leafId)
    setPendingSlot(slot)
  }

  function renderGrid() {
    return (
      <section className="board" aria-label="Word tiles">
        <p className="instruction">Pair the words that share a common ancestor.</p>
        <p className="statusLine" aria-live="polite">{progressText}</p>
        <div className="notes">
          {leaves.map((leaf) => {
            const state = noteStateFor(leaf.id, pairs, pendingId, pendingSlot)
            const slot = state.kind === 'idle' ? null : PAIR_SLOTS[state.slotIndex]
            const tone: PairTone | 'white' = slot?.tone ?? 'white'
            const marker = slot?.marker
            const selected = state.kind === 'pending'
            return (
              <PostIt
                key={leaf.id}
                className="mediumNote"
                tone={tone}
                marker={marker}
                selected={selected}
                placeholder={loading}
                disabled={loading || !puzzle}
                aria-label={
                  loading
                    ? 'Loading word'
                    : `${leaf.lang} ${leaf.term}${marker ? `, pair ${marker}` : ''}`
                }
                onClick={() => handleNoteClick(leaf.id)}
              >
                {loading ? null : (
                  <>
                    <span className="noteLang">{leaf.lang}</span>
                    <span className="noteTerm">{leaf.term}</span>
                  </>
                )}
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
            tone="blue"
            hint={stampHint}
            disabled={!puzzle || pairs.length !== 4 || solveMutation.isPending}
            aria-label="Submit pairs"
            onClick={() => {
              if (!puzzle || pairs.length !== 4) {
                return
              }
              const submitted: [string, string][] = pairs.map((p) => [p.left, p.right])
              submit(puzzle, { id: puzzle.id, pairs: submitted })
            }}
          >
            Submit
          </Stamp>
        )}
      </section>
    )
  }

  return (
    <ModeShell mode="medium" streak={streak} settling={settling} onAnimationEnd={onAnimationEnd}>
      {revealing ? (
        <FeedbackScreen
          mode="medium"
          result={
            solveMutation.data
              ? {
                  correct: solveMutation.data.correct,
                  ancestors: solveMutation.data.ancestors,
                  pairOrigins: solveMutation.data.pairOrigins,
                }
              : undefined
          }
          onNext={handleNext}
        />
      ) : (
        <>
          {renderGrid()}
          {renderSubmit()}
        </>
      )}

    </ModeShell>
  )
}
