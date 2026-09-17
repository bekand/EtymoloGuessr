import { useCallback, useState } from 'react'
import type { PuzzleMode } from '@/api/types'

const STREAK_KEYS: Record<PuzzleMode, string> = {
  easy: 'etymoguessr:easy-streak',
  hard: 'etymoguessr:hard-streak',
}

function parseStreak(raw: string | null): number {
  if (!raw) {
    return 0
  }
  const n = Number.parseInt(raw, 10)
  return Number.isInteger(n) && n > 0 ? n : 0
}

export function readStreak(mode: PuzzleMode): number {
  try {
    return parseStreak(localStorage.getItem(STREAK_KEYS[mode]))
  } catch {
    return 0
  }
}

export function recordStreakResult(mode: PuzzleMode, correct: boolean): number {
  const next = correct ? readStreak(mode) + 1 : 0
  try {
    localStorage.setItem(STREAK_KEYS[mode], String(next))
  } catch {
    // Ignore quota / private-mode failures; callers still get the new count.
  }
  return next
}

export function useStreak(mode: PuzzleMode) {
  const [streak, setStreak] = useState(() => readStreak(mode))

  const recordResult = useCallback(
    (correct: boolean) => {
      setStreak(recordStreakResult(mode, correct))
    },
    [mode],
  )

  return { streak, recordResult }
}
