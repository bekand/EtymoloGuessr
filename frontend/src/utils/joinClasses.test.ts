import { describe, expect, it } from 'vitest'
import { joinClasses } from './joinClasses'

describe('joinClasses', () => {
  it('drops falsy tokens and joins the rest', () => {
    expect(joinClasses('stamp', false, 'lg', null, undefined, 'selected')).toBe('stamp lg selected')
    expect(joinClasses()).toBe('')
  })
})
