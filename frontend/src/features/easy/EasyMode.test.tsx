import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { type ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { EasyMode } from './EasyMode'
import { easyPrompt, easySolve, nextEasyPrompt } from '@/test/fixtures'
import { server } from '@/test/mswServer'

vi.mock('@/ui/graph/EtymologyGraph', () => ({
  EtymologyGraph: () => <div data-testid="gold-graph" />,
}))

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/easy']}>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('EasyMode', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('plays a round and fetches the next puzzle', async () => {
    const user = userEvent.setup()
    let randomCalls = 0
    server.use(
      http.get(/\/puzzles\/random/, () => {
        randomCalls += 1
        return HttpResponse.json(randomCalls === 1 ? easyPrompt : nextEasyPrompt)
      }),
      http.get(/\/puzzles\/(?!random)([^/?]+)/, ({ request }) => {
        const id = new URL(request.url).pathname.split('/').pop()
        return HttpResponse.json(id === nextEasyPrompt.id ? nextEasyPrompt : easyPrompt)
      }),
      http.post(/\/puzzles\/[^/]+\/solve/, async ({ request }) => {
        const body = (await request.json()) as { choiceId?: string }
        return HttpResponse.json({
          ...easySolve,
          correct: body.choiceId === 'c0',
        })
      }),
    )

    render(<EasyMode />, { wrapper })

    expect(await screen.findByRole('article', { name: 'father' })).toBeInTheDocument()
    expect(screen.getByText('EtymoloGuessr')).toBeInTheDocument()
    expect(screen.getByRole('article', { name: 'Vater' })).toBeInTheDocument()
    const choices = screen.getAllByRole('button', { name: /^Choice / })
    expect(choices).toHaveLength(4)
    for (const button of choices) {
      expect(button.querySelector('.marker')).not.toBeNull()
    }
    expect(screen.getByText('Easy', { selector: '.modeLabel' })).toBeInTheDocument()
    expect(screen.getByText('|Streak: 0')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit answer' })).toHaveClass('green')

    const choice = screen.getByRole('button', { name: /a male parent/ })
    await user.click(choice)
    expect(choice).toHaveClass('selected')
    expect(choice.querySelector('.marker')).toHaveTextContent(/^[A-D]$/)
    await user.click(screen.getByRole('button', { name: 'Submit answer' }))

    expect(await screen.findByText(/Correct!/)).toBeInTheDocument()
    expect(screen.getByTestId('gold-graph')).toBeInTheDocument()
    expect(screen.getByText('|Streak: 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load the next puzzle' })).toHaveClass('green')
    await waitFor(() => expect(randomCalls).toBe(2))

    await user.click(screen.getByRole('button', { name: 'Load the next puzzle' }))
    expect(screen.getByRole('article', { name: 'hound' })).toBeInTheDocument()
    expect(screen.queryByText(/Correct!/)).not.toBeInTheDocument()
    expect(screen.getByText('|Streak: 1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /a river/ }))
    await user.click(screen.getByRole('button', { name: 'Submit answer' }))
    expect(await screen.findByText(/Unfortunately, that's not correct/)).toBeInTheDocument()
    expect(screen.getByText('|Streak: 0')).toBeInTheDocument()
  })
})
