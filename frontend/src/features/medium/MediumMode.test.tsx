import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { type ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import { MediumMode } from './MediumMode'
import { mediumPrompt, mediumSolve, nextMediumPrompt } from '@/test/fixtures'
import { server } from '@/test/mswServer'

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/medium']}>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('MediumMode', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('pairs notes, submits with blue stamps, and shows ancestors', async () => {
    const user = userEvent.setup()
    let randomCalls = 0
    server.use(
      http.get(/\/puzzles\/random/, () => {
        randomCalls += 1
        return HttpResponse.json(randomCalls === 1 ? mediumPrompt : nextMediumPrompt)
      }),
      http.get(/\/puzzles\/(?!random)([^/?]+)/, ({ request }) => {
        const id = decodeURIComponent(new URL(request.url).pathname.split('/').pop() ?? '')
        return HttpResponse.json(id === nextMediumPrompt.id ? nextMediumPrompt : mediumPrompt)
      }),
      http.post(/\/puzzles\/[^/]+\/solve/, async ({ request }) => {
        const body = (await request.json()) as { pairs?: [string, string][] }
        const correct =
          Array.isArray(body.pairs) &&
          body.pairs.length === 4 &&
          body.pairs.every(([a, b]) => {
            const pair = [a, b].sort().join('|')
            return (
              pair === 'tok01|tok02' ||
              pair === 'tok03|tok04' ||
              pair === 'tok05|tok06' ||
              pair === 'tok07|tok08'
            )
          })
        return HttpResponse.json({
          ...mediumSolve,
          correct,
        })
      }),
    )

    render(<MediumMode />, { wrapper })

    expect(await screen.findByText('father')).toBeInTheDocument()
    expect(screen.getByText('Medium', { selector: '.modeLabel' })).toBeInTheDocument()
    expect(screen.getByText('0/4 pairs matched')).toBeInTheDocument()
    expect(screen.getByText('|Streak: 0')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Submit pairs' })).toHaveClass('blue')
    expect(screen.getByLabelText('Word tiles').querySelectorAll('button')).toHaveLength(8)

    const clickLeaf = async (term: string) => {
      await user.click(screen.getByRole('button', { name: new RegExp(term) }))
    }

    await clickLeaf('father')
    expect(screen.getByRole('button', { name: /father/ })).toHaveTextContent('A?')
    await clickLeaf('Vater')
    expect(screen.getByRole('button', { name: /Vater/ })).toHaveTextContent('A?')
    expect(screen.getByRole('button', { name: /father/ })).toHaveClass('yellow')
    expect(screen.getByRole('button', { name: /Vater/ })).toHaveClass('yellow')

    await clickLeaf('hound')
    await clickLeaf('Hund')
    await clickLeaf('gift')
    await clickLeaf('Gift')
    await clickLeaf('house')
    await clickLeaf('Haus')

    await user.click(screen.getByRole('button', { name: 'Submit pairs' }))

    expect(await screen.findByText(/Correct!/)).toBeInTheDocument()
    expect(screen.getByLabelText('Shared ancestors')).toBeInTheDocument()
    expect(screen.queryByTestId('gold-graph')).not.toBeInTheDocument()
    expect(screen.getByText('*fader')).toBeInTheDocument()
    expect(screen.getByText('|Streak: 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load the next puzzle' })).toHaveClass('blue')
    await waitFor(() => expect(randomCalls).toBe(2))

    await user.click(screen.getByRole('button', { name: 'Load the next puzzle' }))
    expect(screen.getByText('father-next')).toBeInTheDocument()
    expect(screen.queryByText(/Correct!/)).not.toBeInTheDocument()

    await clickLeaf('father-next')
    await clickLeaf('hound-next')
    await clickLeaf('Vater-next')
    await clickLeaf('Hund-next')
    await clickLeaf('gift-next')
    await clickLeaf('Gift-next')
    await clickLeaf('house-next')
    await clickLeaf('Haus-next')
    await user.click(screen.getByRole('button', { name: 'Submit pairs' }))
    expect(await screen.findByText(/Unfortunately, that's not correct/)).toBeInTheDocument()
    expect(screen.getByText('|Streak: 0')).toBeInTheDocument()
  })
})
