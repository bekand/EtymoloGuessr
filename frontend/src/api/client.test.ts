import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { ApiError, apiJson } from './client'
import { server } from '@/test/mswServer'

describe('apiJson', () => {
  it('raises ApiError with the body error message', async () => {
    server.use(
      http.get(/\/boom$/, () => HttpResponse.json({ error: 'database unavailable' }, { status: 503 })),
    )
    const err = await apiJson('/boom').catch((caught: unknown) => caught)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 503, message: 'database unavailable' })
  })
})
