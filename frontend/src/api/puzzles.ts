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

const RECENT_IDS_KEY = 'etymologuessr:recent-puzzle-ids'
const RECENT_IDS_MAX = 10

export function isPuzzleNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

export function readRecentPuzzleIds(): string[] {
  try {
    const raw = sessionStorage.getItem(RECENT_IDS_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) {
      sessionStorage.removeItem(RECENT_IDS_KEY)
      return []
    }
    return parsed.filter((id): id is string => typeof id === 'string' && id.length > 0).slice(-RECENT_IDS_MAX)
  } catch {
    sessionStorage.removeItem(RECENT_IDS_KEY)
    return []
  }
}

export function pushRecentPuzzleId(id: string): void {
  const trimmed = id.trim()
  if (!trimmed) {
    return
  }
  const next = readRecentPuzzleIds().filter((existing) => existing !== trimmed)
  next.push(trimmed)
  sessionStorage.setItem(RECENT_IDS_KEY, JSON.stringify(next.slice(-RECENT_IDS_MAX)))
}

/** Expand a medium set id into its component puzzle ids; otherwise return [id]. */
export function recentIdsFromPuzzleId(id: string): string[] {
  const parts = id.split(',').map((p) => p.trim()).filter(Boolean)
  if (parts.length === 4) {
    return parts
  }
  return id.trim() ? [id.trim()] : []
}

function pushRecentFromPuzzleId(id: string): void {
  for (const part of recentIdsFromPuzzleId(id)) {
    pushRecentPuzzleId(part)
  }
}

function randomPuzzleUrl(mode: PuzzleMode): string {
  const params = new URLSearchParams({ mode })
  const recent = readRecentPuzzleIds()
  if (recent.length > 0) {
    params.set('exclude', recent.join(','))
  }
  return `/puzzles/random?${params.toString()}`
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
  return apiJson(randomPuzzleUrl(mode))
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
  pushRecentFromPuzzleId(puzzle.id)
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
  pushRecentFromPuzzleId(puzzle.id)
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
