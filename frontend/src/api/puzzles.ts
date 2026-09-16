import { ApiError, apiJson } from '@/api/client'
import type { GraphEdge, PuzzleMode, PuzzlePrompt, SolveResponse } from '@/api/types'

export const puzzleKeys = {
  randomEasy: ['puzzles', 'random', 'easy'] as const,
  randomHard: ['puzzles', 'random', 'hard'] as const,
}

const LOCK_KEYS: Record<PuzzleMode, string> = {
  easy: 'etymoguessr:easy-puzzle',
  hard: 'etymoguessr:hard-puzzle',
}

export function isPuzzleNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

function isValidLock(mode: PuzzleMode, parsed: PuzzlePrompt): boolean {
  if (!parsed?.id || !parsed.leafA || !parsed.leafB || !Array.isArray(parsed.choices)) {
    return false
  }
  if (mode === 'hard') {
    return Boolean(parsed.promptGraph && Array.isArray(parsed.promptGraph.nodes))
  }
  return true
}

export function readPuzzleLock(mode: PuzzleMode): PuzzlePrompt | null {
  const key = LOCK_KEYS[mode]
  try {
    const raw = localStorage.getItem(key)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as PuzzlePrompt
    if (!isValidLock(mode, parsed)) {
      localStorage.removeItem(key)
      return null
    }
    return parsed
  } catch {
    localStorage.removeItem(key)
    return null
  }
}

export function writePuzzleLock(mode: PuzzleMode, puzzle: PuzzlePrompt): void {
  localStorage.setItem(LOCK_KEYS[mode], JSON.stringify(puzzle))
}

export function clearPuzzleLock(mode: PuzzleMode): void {
  localStorage.removeItem(LOCK_KEYS[mode])
}

export function readEasyPuzzleLock(): PuzzlePrompt | null {
  return readPuzzleLock('easy')
}

export function writeEasyPuzzleLock(puzzle: PuzzlePrompt): void {
  writePuzzleLock('easy', puzzle)
}

export function clearEasyPuzzleLock(): void {
  clearPuzzleLock('easy')
}

export function readHardPuzzleLock(): PuzzlePrompt | null {
  return readPuzzleLock('hard')
}

export function writeHardPuzzleLock(puzzle: PuzzlePrompt): void {
  writePuzzleLock('hard', puzzle)
}

export function clearHardPuzzleLock(): void {
  clearPuzzleLock('hard')
}

export function fetchRandomPuzzle(mode: PuzzleMode): Promise<PuzzlePrompt> {
  return apiJson(`/puzzles/random?mode=${mode}`)
}

export function fetchPuzzleById(id: string, mode: PuzzleMode): Promise<PuzzlePrompt> {
  return apiJson(`/puzzles/${encodeURIComponent(id)}?mode=${mode}`)
}

async function fetchLockedRandom(mode: PuzzleMode): Promise<PuzzlePrompt> {
  const locked = readPuzzleLock(mode)
  if (locked) {
    try {
      const live = await fetchPuzzleById(locked.id, mode)
      writePuzzleLock(mode, live)
      return live
    } catch (error) {
      if (!isPuzzleNotFound(error)) {
        throw error
      }
      clearPuzzleLock(mode)
    }
  }
  const puzzle = await fetchRandomPuzzle(mode)
  writePuzzleLock(mode, puzzle)
  return puzzle
}

export function fetchLockedRandomEasy(): Promise<PuzzlePrompt> {
  return fetchLockedRandom('easy')
}

export function fetchLockedRandomHard(): Promise<PuzzlePrompt> {
  return fetchLockedRandom('hard')
}

async function solveOrClearLock<T>(mode: PuzzleMode, request: Promise<T>): Promise<T> {
  try {
    return await request
  } catch (error) {
    if (isPuzzleNotFound(error)) {
      clearPuzzleLock(mode)
    }
    throw error
  }
}

export function solveEasyPuzzle(id: string, choiceId: string): Promise<SolveResponse> {
  return solveOrClearLock(
    'easy',
    apiJson(`/puzzles/${encodeURIComponent(id)}/solve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'easy', choiceId }),
    }),
  )
}

export function solveHardPuzzle(id: string, edges: GraphEdge[]): Promise<SolveResponse> {
  return solveOrClearLock(
    'hard',
    apiJson(`/puzzles/${encodeURIComponent(id)}/solve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'hard', edges }),
    }),
  )
}
