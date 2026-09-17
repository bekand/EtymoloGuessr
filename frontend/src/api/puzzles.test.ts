import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it } from 'vitest'
import { ApiError } from '@/api/client'
import {
  fetchLockedRandomEasy,
  fetchLockedRandomHard,
  readPuzzleLock,
  solveEasyPuzzle,
  writePuzzleLock,
} from '@/api/puzzles'
import { easyPrompt, hardPrompt } from '@/test/fixtures'
import { server } from '@/test/mswServer'

afterEach(() => {
  localStorage.clear()
})

describe('puzzle lock', () => {
  it('refetches the locked id instead of random', async () => {
    writePuzzleLock('easy', easyPrompt)
    const seen: string[] = []
    server.use(
      http.get(/\/puzzles\/random/, () => {
        seen.push('random')
        return HttpResponse.json(easyPrompt)
      }),
      http.get(/\/puzzles\/(?!random)([^/?]+)/, ({ request }) => {
        const id = new URL(request.url).pathname.split('/').pop() ?? ''
        seen.push(id)
        return HttpResponse.json({ ...easyPrompt, id })
      }),
    )

    const live = await fetchLockedRandomEasy()
    expect(live.id).toBe(easyPrompt.id)
    expect(seen).toEqual([easyPrompt.id])
    expect(readPuzzleLock('easy')?.id).toBe(easyPrompt.id)
  })

  it('discards a hard lock that has no promptGraph', async () => {
    writePuzzleLock('hard', { ...hardPrompt, promptGraph: undefined })
    expect(readPuzzleLock('hard')).toBeNull()

    server.use(
      http.get(/\/puzzles\/random/, () => HttpResponse.json(hardPrompt)),
    )
    const live = await fetchLockedRandomHard()
    expect(live.id).toBe(hardPrompt.id)
    expect(readPuzzleLock('hard')?.promptGraph?.nodes).toHaveLength(4)
  })

  it('clears the lock on 404 fetch and solve', async () => {
    writePuzzleLock('easy', easyPrompt)
    server.use(
      http.get(/\/puzzles\/(?!random)([^/?]+)/, () =>
        HttpResponse.json({ error: 'puzzle not found' }, { status: 404 }),
      ),
      http.get(/\/puzzles\/random/, () => HttpResponse.json(easyPrompt)),
    )
    await fetchLockedRandomEasy()
    expect(readPuzzleLock('easy')?.id).toBe(easyPrompt.id)

    writePuzzleLock('easy', easyPrompt)
    server.use(
      http.post(/\/puzzles\/[^/]+\/solve/, () =>
        HttpResponse.json({ error: 'puzzle not found' }, { status: 404 }),
      ),
    )
    await expect(solveEasyPuzzle(easyPrompt.id, 'c0')).rejects.toBeInstanceOf(ApiError)
    expect(readPuzzleLock('easy')).toBeNull()
  })
})
