import { apiJson } from '@/api/client'
import type { PuzzleMode, PuzzlePrompt, SolveResponse } from '@/api/types'

export const puzzleKeys = {
  randomEasy: ['puzzles', 'random', 'easy'] as const,
}

const EASY_PUZZLE_LOCK_KEY = 'etymoguessr:easy-puzzle'

export function readEasyPuzzleLock(): PuzzlePrompt | null {
  try {
    const raw = localStorage.getItem(EASY_PUZZLE_LOCK_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as PuzzlePrompt
    if (!parsed?.id || !parsed.leafA || !parsed.leafB || !Array.isArray(parsed.choices)) {
      localStorage.removeItem(EASY_PUZZLE_LOCK_KEY)
      return null
    }
    return parsed
  } catch {
    localStorage.removeItem(EASY_PUZZLE_LOCK_KEY)
    return null
  }
}

export function writeEasyPuzzleLock(puzzle: PuzzlePrompt): void {
  localStorage.setItem(EASY_PUZZLE_LOCK_KEY, JSON.stringify(puzzle))
}

export function clearEasyPuzzleLock(): void {
  localStorage.removeItem(EASY_PUZZLE_LOCK_KEY)
}

export function fetchRandomPuzzle(mode: PuzzleMode): Promise<PuzzlePrompt> {
  return apiJson(`/puzzles/random?mode=${mode}`)
}

export async function fetchLockedRandomEasy(): Promise<PuzzlePrompt> {
  const locked = readEasyPuzzleLock()
  if (locked) {
    return locked
  }
  const puzzle = await fetchRandomPuzzle('easy')
  writeEasyPuzzleLock(puzzle)
  return puzzle
}

export function solveEasyPuzzle(id: string, choiceId: string): Promise<SolveResponse> {
  return apiJson(`/puzzles/${encodeURIComponent(id)}/solve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: 'easy', choiceId }),
  })
}
