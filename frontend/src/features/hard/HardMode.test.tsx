import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { type ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { HardMode } from './HardMode'
import { hardPrompt } from '@/test/fixtures'
import { server } from '@/test/mswServer'
import { http, HttpResponse } from 'msw'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/hard']}>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('HardMode', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('shows a concrete progress count while placing cards', async () => {
    server.use(
      http.get(/\/puzzles\/random/, () => HttpResponse.json(hardPrompt)),
    )

    render(<HardMode />, { wrapper })

    expect(await screen.findByText('0/4 cards placed')).toBeInTheDocument()
    expect(screen.getByText('Place every card on the blotter, then draw lines from descendant to ancestor.')).toBeInTheDocument()
  })
})
