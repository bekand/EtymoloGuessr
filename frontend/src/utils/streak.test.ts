import { describe, expect, it } from 'vitest'
import { readStreak, recordStreakResult } from './streak'

describe('streak', () => {
  it('starts at zero and keeps easy, hard, and medium counts separate', () => {
    expect(readStreak('easy')).toBe(0)
    expect(readStreak('hard')).toBe(0)
    expect(readStreak('medium')).toBe(0)

    localStorage.setItem('etymologuessr:easy-streak', 'nope')
    expect(readStreak('easy')).toBe(0)

    expect(recordStreakResult('easy', true)).toBe(1)
    expect(recordStreakResult('easy', true)).toBe(2)
    expect(recordStreakResult('hard', true)).toBe(1)
    expect(recordStreakResult('medium', true)).toBe(1)
    expect(recordStreakResult('medium', true)).toBe(2)
    expect(readStreak('easy')).toBe(2)
    expect(readStreak('hard')).toBe(1)
    expect(readStreak('medium')).toBe(2)

    expect(recordStreakResult('easy', false)).toBe(0)
    expect(readStreak('easy')).toBe(0)
    expect(readStreak('hard')).toBe(1)
    expect(readStreak('medium')).toBe(2)
  })
})
