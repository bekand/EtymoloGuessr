import { ApiError, apiJson } from '@/api/client'
import type {
  GraphEdge,
  MediumPrompt,
  PuzzleMode,
  PuzzlePrompt,
  SolveResponse,
} from '@/api/types'

export const puzzleKeys = {
  randomEasy: ['puzzles', 'random', 'easy'] as const,
  randomHard: ['puzzles', 'random', 'hard'] as const,
  randomMedium: ['puzzles', 'random', 'medium'] as const,
}

const LOCK_KEYS: Record<PuzzleMode, string> = {
  easy: 'etymologuessr:easy-puzzle',
  hard: 'etymologuessr:hard-puzzle',
  medium: 'etymologuessr:medium-puzzle',
}

export function isPuzzleNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

function isValidEasyHardLock(parsed: PuzzlePrompt): boolean {
  return Boolean(parsed?.id && parsed.leafA && parsed.leafB && Array.isArray(parsed.choices))
}

function isValidMediumLock(parsed: MediumPrompt): boolean {
  return (
    Boolean(parsed?.id) &&
    parsed.mode === 'medium' &&
    Array.isArray(parsed.leaves) &&
    parsed.leaves.length === 8 &&
    parsed.leaves.every((leaf) => leaf?.id && leaf.lang && leaf.term)
  )
}

function isValidLock(mode: PuzzleMode, parsed: PuzzlePrompt | MediumPrompt): boolean {
  if (mode === 'medium') {
    return isValidMediumLock(parsed as MediumPrompt)
  }
  const prompt = parsed as PuzzlePrompt
  if (!isValidEasyHardLock(prompt)) {
    return false
  }
  if (mode === 'hard') {
    return Boolean(prompt.promptGraph && Array.isArray(prompt.promptGraph.nodes))
  }
  return true
}

export function readPuzzleLock(mode: 'easy' | 'hard'): PuzzlePrompt | null
export function readPuzzleLock(mode: 'medium'): MediumPrompt | null
export function readPuzzleLock(mode: PuzzleMode): PuzzlePrompt | MediumPrompt | null {
  const key = LOCK_KEYS[mode]
  try {
    const raw = localStorage.getItem(key)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as PuzzlePrompt | MediumPrompt
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

export function writePuzzleLock(mode: 'easy' | 'hard', puzzle: PuzzlePrompt): void
export function writePuzzleLock(mode: 'medium', puzzle: MediumPrompt): void
export function writePuzzleLock(mode: PuzzleMode, puzzle: PuzzlePrompt | MediumPrompt): void {
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

export function fetchRandomPuzzle(mode: 'easy' | 'hard'): Promise<PuzzlePrompt>
export function fetchRandomPuzzle(mode: 'medium'): Promise<MediumPrompt>
export function fetchRandomPuzzle(mode: PuzzleMode): Promise<PuzzlePrompt | MediumPrompt> {
  return apiJson(`/puzzles/random?mode=${mode}`)
}

export function fetchPuzzleById(id: string, mode: 'easy' | 'hard'): Promise<PuzzlePrompt>
export function fetchPuzzleById(id: string, mode: 'medium'): Promise<MediumPrompt>
export function fetchPuzzleById(id: string, mode: PuzzleMode): Promise<PuzzlePrompt | MediumPrompt> {
  return apiJson(`/puzzles/${encodeURIComponent(id)}?mode=${mode}`)
}

async function fetchLockedRandomEasyHard(mode: 'easy' | 'hard'): Promise<PuzzlePrompt> {
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
  return fetchLockedRandomEasyHard('easy')
}

export function fetchLockedRandomHard(): Promise<PuzzlePrompt> {
  return fetchLockedRandomEasyHard('hard')
}

export function fetchLockedRandomMedium(): Promise<MediumPrompt> {
  return fetchLockedMedium()
}

async function fetchLockedMedium(): Promise<MediumPrompt> {
  const locked = readPuzzleLock('medium')
  if (locked) {
    try {
      const live = await fetchPuzzleById(locked.id, 'medium')
      writePuzzleLock('medium', live)
      return live
    } catch (error) {
      if (!isPuzzleNotFound(error)) {
        throw error
      }
      clearPuzzleLock('medium')
    }
  }
  const puzzle = await fetchRandomPuzzle('medium')
  writePuzzleLock('medium', puzzle)
  return puzzle
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

export function solveMediumPuzzle(id: string, pairs: [string, string][]): Promise<SolveResponse> {
  return solveOrClearLock(
    'medium',
    apiJson(`/puzzles/${encodeURIComponent(id)}/solve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'medium', pairs }),
    }),
  )
}
