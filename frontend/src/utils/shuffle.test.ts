import { describe, expect, it } from 'vitest'
import { shuffle } from './shuffle'

describe('shuffle', () => {
  it('returns the same order for the same id', () => {
    const items = ['a', 'b', 'c', 'd']
    expect(shuffle(items, 'p1-same')).toEqual(shuffle(items, 'p1-same'))
  })

  it('leaves empty and singleton lists unchanged', () => {
    expect(shuffle([], 'p1')).toEqual([])
    expect(shuffle(['only'], 'p1')).toEqual(['only'])
  })
})
