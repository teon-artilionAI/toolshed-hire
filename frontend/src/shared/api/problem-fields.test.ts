/**
 * Tests for turning a 422 into one message per field.
 *
 * Each test builds the error a failed call would throw and checks the lookup a
 * form would index into.
 */

import { describe, expect, it } from 'vitest'
import { ApiError } from '../api-problem'
import { fieldErrorsFromProblem, otherFieldMessages } from './problem-fields'

function refusal(errors: Record<string, unknown> | undefined, status = 422): ApiError {
  return new ApiError({
    kind: 'problem',
    status,
    title: 'Unprocessable Entity',
    detail: 'The request did not pass validation.',
    requestPath: '/api/catalogue/availability',
    problem: {
      type: 'https://toolshedhire.co.za/problems/request-validation-failure',
      title: 'Unprocessable Entity',
      status,
      detail: 'The request did not pass validation.',
      errors,
    },
  })
}

describe('fieldErrorsFromProblem', () => {
  it('gives each refused field its message', () => {
    const errors = fieldErrorsFromProblem(
      refusal({ from: 'Must be today or later.', to: 'Must be after the collection date.' }),
    )

    expect(errors).toEqual({
      from: 'Must be today or later.',
      to: 'Must be after the collection date.',
    })
  })

  it('joins several messages for one field into one sentence run', () => {
    const errors = fieldErrorsFromProblem(
      refusal({ password: ['Use 12 characters or more.', 'Add a number.'] }),
    )

    expect(errors.password).toBe('Use 12 characters or more. Add a number.')
  })

  it('reads the messages the API nests under fields, by the bare field name', () => {
    const errors = fieldErrorsFromProblem(
      refusal({ fields: { 'query.from': 'Input should be a valid date.', 'query.quantity': 'Too many.' } }),
    )

    expect(errors).toEqual({ from: 'Input should be a valid date.', quantity: 'Too many.' })
  })

  it('puts the refusal of a return date, exactly as the API words it, under to', () => {
    const sentence =
      'A hire period may not exceed 28 days. Attempted start=2026-10-10 end=2026-11-20, which is 41 days.'
    const errors = fieldErrorsFromProblem(refusal({ fields: { 'query.to': sentence } }))

    expect(errors).toEqual({ to: sentence })
    expect(otherFieldMessages(errors, ['from', 'to'])).toEqual([])
  })

  it('strips where the value came from, and keeps the rest of a nested name', () => {
    const errors = fieldErrorsFromProblem(
      refusal({ 'body.email': 'Not an email address.', 'body.lines.0.quantity': 'Must be 1 or more.' }),
    )

    expect(errors).toEqual({
      email: 'Not an email address.',
      'lines.0.quantity': 'Must be 1 or more.',
    })
  })

  it('leaves a field that only looks like a location alone', () => {
    expect(fieldErrorsFromProblem(refusal({ query: 'Too short.' }))).toEqual({ query: 'Too short.' })
  })

  it('still marks a field whose message is not text', () => {
    const errors = fieldErrorsFromProblem(refusal({ quantity: { limit: 10 } }))

    expect(errors.quantity).toBe('This value was not accepted.')
  })

  it('keeps the first message when a field is named twice', () => {
    const errors = fieldErrorsFromProblem(
      refusal({ from: 'Must be today or later.', fields: { 'query.from': 'A second opinion.' } }),
    )

    expect(errors.from).toBe('Must be today or later.')
  })

  it('is empty for a 422 that names no fields', () => {
    expect(fieldErrorsFromProblem(refusal(undefined))).toEqual({})
  })

  it('is empty for a failure that is not a 422', () => {
    expect(fieldErrorsFromProblem(refusal({ unitId: 'already allocated' }, 409))).toEqual({})
  })

  it('is empty for something that is not an API failure at all', () => {
    expect(fieldErrorsFromProblem(new TypeError('boom'))).toEqual({})
    expect(fieldErrorsFromProblem(null)).toEqual({})
  })
})

describe('otherFieldMessages', () => {
  it('returns the messages a form has no input for', () => {
    const errors = { from: 'Must be today or later.', pageSize: 'Must be 50 or fewer.' }

    expect(otherFieldMessages(errors, ['from', 'to'])).toEqual(['Must be 50 or fewer.'])
  })

  it('is empty when the form shows every message itself', () => {
    expect(otherFieldMessages({ from: 'Must be today or later.' }, ['from', 'to'])).toEqual([])
  })
})
