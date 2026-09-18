import { useState } from 'react'
import { noop, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  clearPuzzleLock,
  fetchLockedRandomEasy,
  fetchLockedRandomHard,
  fetchLockedRandomMedium,
  isPuzzleNotFound,
  puzzleKeys,
} from '@/api/puzzles'
import type { MediumPrompt, PuzzleMode, PuzzlePrompt, SolveResponse } from '@/api/types'
import { useStreak } from '@/utils/streak'

type PromptByMode = {
  easy: PuzzlePrompt
  hard: PuzzlePrompt
  medium: MediumPrompt
}

type RandomPuzzleQuery<M extends PuzzleMode> = {
  queryKey: readonly ['puzzles', 'random', M]
  queryFn: () => Promise<PromptByMode[M]>
  staleTime: number
  gcTime: number
  refetchOnWindowFocus: false
  refetchOnReconnect: false
  refetchOnMount: false
}

const queryDefaults = {
  staleTime: Infinity,
  gcTime: Infinity,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  refetchOnMount: false,
} as const

const randomPuzzleQuery = {
  easy: {
    queryKey: puzzleKeys.randomEasy,
    queryFn: fetchLockedRandomEasy,
    ...queryDefaults,
  },
  hard: {
    queryKey: puzzleKeys.randomHard,
    queryFn: fetchLockedRandomHard,
    ...queryDefaults,
  },
  medium: {
    queryKey: puzzleKeys.randomMedium,
    queryFn: fetchLockedRandomMedium,
    ...queryDefaults,
  },
} satisfies { [M in PuzzleMode]: RandomPuzzleQuery<M> }

export function useSolvePuzzle<M extends PuzzleMode, TVariables>(
  mode: M,
  mutationFn: (variables: TVariables) => Promise<SolveResponse>,
  onPuzzleGone?: () => void,
) {
  const queryClient = useQueryClient()
  const [gradedPuzzle, setGradedPuzzle] = useState<PromptByMode[M]>()
  const { streak, recordResult } = useStreak(mode)
  const nextQuery = randomPuzzleQuery[mode] as RandomPuzzleQuery<M>

  const solveMutation = useMutation({
    mutationFn,
    onSuccess: (result) => {
      recordResult(result.correct)
      clearPuzzleLock(mode)
      queryClient.removeQueries({ queryKey: nextQuery.queryKey })
      void queryClient.query(nextQuery).catch(noop)
    },
    onError: (error) => {
      if (!isPuzzleNotFound(error)) {
        return
      }
      setGradedPuzzle(undefined)
      onPuzzleGone?.()
      queryClient.removeQueries({ queryKey: nextQuery.queryKey })
    },
  })
  const solved = solveMutation.isSuccess
  const revealing = solveMutation.isPending || solved

  const puzzleQuery = useQuery({
    ...nextQuery,
    enabled: !solved,
  })

  const puzzle = gradedPuzzle ?? puzzleQuery.data
  const loading = !puzzle && puzzleQuery.isPending
  const loadError = !puzzle && puzzleQuery.isError

  function submit(current: PromptByMode[M], variables: TVariables) {
    setGradedPuzzle(current)
    solveMutation.mutate(variables)
  }

  function next() {
    setGradedPuzzle(undefined)
    solveMutation.reset()
  }

  return {
    puzzle,
    puzzleQuery,
    solveMutation,
    revealing,
    loading,
    loadError,
    streak,
    submit,
    next,
  }
}
