/**
 * Tests for the rules of the owner's corrections before anything is sent.
 */

import { describe, expect, it } from 'vitest'
import { amountForTheWire, amountProblem, reasonProblem } from './correction-model'

describe('a reason', () => {
  it('is needed, and needs five characters or more once the spaces around it are gone', () => {
    expect(reasonProblem('   ')).toMatch(/^Write the reason/)
    expect(reasonProblem('  Oops ')).toBe('Write at least 5 characters. This has 4.')
    expect(reasonProblem('Typed twice')).toBeNull()
  })

  it('is kept to two hundred characters', () => {
    expect(reasonProblem('a'.repeat(200))).toBeNull()
    expect(reasonProblem('a'.repeat(201))).toBe('Keep the reason to 200 characters. This has 201.')
  })
})

describe('the amount of an adjustment', () => {
  it('is written with two decimals, by its digits', () => {
    expect(amountForTheWire('150')).toBe('150.00')
    expect(amountForTheWire(' -150.5 ')).toBe('-150.50')
    expect(amountForTheWire('-0150,25')).toBe('-150.25')
    expect(amountForTheWire('12345678901234567890.99')).toBe('12345678901234567890.99')
    expect(amountForTheWire('R150')).toBeNull()
    expect(amountForTheWire('1.234')).toBeNull()
  })

  it('is needed, has to be money and cannot be zero', () => {
    expect(amountProblem('', false)).toMatch(/^Enter the amount/)
    expect(amountProblem('ten', false)).toMatch(/^Enter rand and cents only/)
    expect(amountProblem('-0.00', false)).toMatch(/^An adjustment of nothing changes nothing/)
    expect(amountProblem('-150', false)).toBeNull()
    expect(amountProblem('150', false)).toBeNull()
  })

  it('can only give money back once the hire is settled', () => {
    expect(amountProblem('150', true)).toMatch(/^This hire is settled, so it can only give money back\./)
    expect(amountProblem('-150', true)).toBeNull()
  })
})
