import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { POST_IT_MAX_TILT_DEG, POST_IT_MIN_TILT_DEG, PostIt } from './PostIt'

afterEach(() => {
  vi.restoreAllMocks()
})

function aabbProtrusion(width: number, height: number, deg: number) {
  const theta = (deg * Math.PI) / 180
  const cos = Math.abs(Math.cos(theta))
  const sin = Math.abs(Math.sin(theta))
  return {
    dx: (width / 2) * (cos - 1) + (height / 2) * sin,
    dy: (height / 2) * (cos - 1) + (width / 2) * sin,
  }
}

describe('PostIt', () => {
  it('maps Math.random into a stable --post-it-tilt', () => {
    vi.spyOn(Math, 'random').mockReturnValueOnce(0).mockReturnValueOnce(0.5)

    const { rerender } = render(
      <>
        <PostIt>one</PostIt>
        <PostIt>two</PostIt>
      </>,
    )

    const [first, second] = screen.getAllByRole('button')
    expect(first?.style.getPropertyValue('--post-it-tilt')).toBe(`-${POST_IT_MIN_TILT_DEG}deg`)
    expect(second?.style.getPropertyValue('--post-it-tilt')).toBe(`${POST_IT_MIN_TILT_DEG}deg`)
    expect(Math.random).toHaveBeenCalledTimes(2)

    rerender(
      <>
        <PostIt>one</PostIt>
        <PostIt>two</PostIt>
      </>,
    )
    expect(first?.style.getPropertyValue('--post-it-tilt')).toBe(`-${POST_IT_MIN_TILT_DEG}deg`)
    expect(second?.style.getPropertyValue('--post-it-tilt')).toBe(`${POST_IT_MIN_TILT_DEG}deg`)
    expect(Math.random).toHaveBeenCalledTimes(2)
  })

  it('keeps tilted notes inside the notes grid gap', () => {
    const rem = 16
    // EasyMode.scss / HardMode.scss `.notes { gap: var(--space-3) }` → 0.75rem
    const gap = 0.75 * rem
    // PostIt.scss hover `translateY(-1px)`
    const hoverLift = 1
    // EasyMode.scss column cap `15.75rem`; HardMode.scss palette/notes cap `16rem`
    const easyWidth = 15.75 * rem
    const hardWidth = 16 * rem
    // PostIt.scss: space-5 + space-4 padding and 6-line body at text-base / 1.4
    const maxHeight = (1.5 + 1 + 6 * 1.0625 * 1.4) * rem + 2

    for (const width of [easyWidth, hardWidth]) {
      const { dx, dy } = aabbProtrusion(width, maxHeight, POST_IT_MAX_TILT_DEG)
      expect(2 * dx).toBeLessThan(gap)
      expect(2 * dy + hoverLift).toBeLessThan(gap)
    }
  })
})
