import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Stamp } from './Stamp'

afterEach(() => {
  vi.useRealTimers()
})

describe('Stamp', () => {
  it('waits for the touch press animation before activating', () => {
    vi.useFakeTimers()
    const onClick = vi.fn()
    render(<Stamp onClick={onClick}>Play</Stamp>)
    const button = screen.getByRole('button', { name: 'Play' })

    fireEvent.pointerUp(button, { pointerType: 'touch' })
    fireEvent.click(button)

    expect(onClick).not.toHaveBeenCalled()
    vi.advanceTimersByTime(159)
    expect(onClick).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onClick).toHaveBeenCalledOnce()
  })
})