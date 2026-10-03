/**
 * Tests for the rules of the handover form and the body it is sent as.
 *
 * The body holds every allocation of the reservation exactly once, in its
 * order, with what was recorded about it and the agreement signed. The rules
 * hold back a form whose tags were not read, whose meter is missing or runs
 * backwards, or whose agreement is not signed.
 */

import { describe, expect, it } from 'vitest'
import { READY_CHECKOUT } from '../../test/counter-samples'
import {
  AGREEMENT_ID,
  draftFor,
  handoverSentence,
  serverErrorsByControl,
  toCheckoutRequest,
  unitControlId,
  validateCheckout,
} from './checkout-form'
import type { CheckoutDraft } from './checkout-form'

const [METERED, PLAIN] = READY_CHECKOUT.units

/** Every tag read and the agreement signed, with the meter as it opened. */
function filledIn(): CheckoutDraft {
  const draft = draftFor(READY_CHECKOUT)
  return {
    agreementSigned: true,
    units: Object.fromEntries(
      Object.entries(draft.units).map(([allocationId, unit]) => [allocationId, { ...unit, tagRead: true }]),
    ),
  }
}

describe('the form a checkout opens with', () => {
  it('starts each unit at the grade it has now and its meter at the last reading, with nothing ticked', () => {
    const draft = draftFor(READY_CHECKOUT)

    expect(draft.agreementSigned).toBe(false)
    expect(draft.units[METERED.allocationId]).toEqual({ tagRead: false, conditionOut: 'B', accessories: '', meter: '1250' })
    expect(draft.units[PLAIN.allocationId]).toEqual({ tagRead: false, conditionOut: 'A', accessories: '', meter: '' })
  })
})

describe('checking the form', () => {
  it('passes a form with every tag read and the agreement signed', () => {
    expect(validateCheckout(READY_CHECKOUT, filledIn())).toEqual({})
  })

  it('asks for every tag to be read and the agreement to be signed', () => {
    const errors = validateCheckout(READY_CHECKOUT, draftFor(READY_CHECKOUT))

    expect(Object.keys(errors).sort()).toEqual([AGREEMENT_ID, unitControlId(0, 'tag'), unitControlId(1, 'tag')].sort())
    expect(errors[unitControlId(0, 'tag')]).toMatch(/If it does not say TSH-PC-0007, stop/)
    expect(errors[AGREEMENT_ID]).toMatch(/signs the hire agreement/)
  })

  it.each([
    ['', /whole hours/],
    ['12.5', /whole hours/],
    ['1249', /cannot read less than the last reading, 1250 hours/],
  ])('refuses a meter reading of "%s"', (meter, message) => {
    const draft = filledIn()
    draft.units[METERED.allocationId] = { ...draft.units[METERED.allocationId], meter }

    expect(validateCheckout(READY_CHECKOUT, draft)).toEqual({ [unitControlId(0, 'meter')]: expect.stringMatching(message) })
  })

  it('refuses accessories longer than the API keeps', () => {
    const draft = filledIn()
    draft.units[PLAIN.allocationId] = { ...draft.units[PLAIN.allocationId], accessories: 'x'.repeat(201) }

    expect(Object.keys(validateCheckout(READY_CHECKOUT, draft))).toEqual([unitControlId(1, 'accessories')])
  })
})

describe('the body a handover is sent as', () => {
  it('holds every allocation once, in order, with the agreement signed', () => {
    const draft = filledIn()
    draft.units[METERED.allocationId] = { ...draft.units[METERED.allocationId], conditionOut: 'C', meter: ' 1262 ' }
    draft.units[PLAIN.allocationId] = { ...draft.units[PLAIN.allocationId], accessories: '  Chuck key and two bits ' }

    expect(toCheckoutRequest(READY_CHECKOUT, draft)).toEqual({
      items: [
        { allocationId: METERED.allocationId, conditionOut: 'C', accessoriesOut: null, hourMeterOut: 1262 },
        { allocationId: PLAIN.allocationId, conditionOut: 'A', accessoriesOut: 'Chuck key and two bits', hourMeterOut: null },
      ],
      agreementSigned: true,
    })
  })

  it('refuses to build a body whose agreement is not signed', () => {
    expect(() => toCheckoutRequest(READY_CHECKOUT, { ...filledIn(), agreementSigned: false })).toThrow(
      /agreement is not signed/,
    )
  })
})

describe('what the API refused', () => {
  it('lands under the control it names, and the rest is listed', () => {
    const { byControl, leftOver } = serverErrorsByControl({
      'items.1.hourMeterOut': 'The meter went backwards.',
      agreementSigned: 'The agreement must be signed.',
      items: 'Every allocation must be checked out exactly once.',
    })

    expect(byControl).toEqual({
      [unitControlId(1, 'meter')]: 'The meter went backwards.',
      [AGREEMENT_ID]: 'The agreement must be signed.',
    })
    expect(leftOver).toEqual(['Every allocation must be checked out exactly once.'])
  })
})

describe('the sentence before the last button', () => {
  it('says what will go out, to whom, the deposit and when it is due back', () => {
    expect(handoverSentence(READY_CHECKOUT)).toMatch(
      /^2 units, TSH-PC-0007, TSH-PC-0011, will go out to Thandi Mokoena from Bellville\. A deposit of R 5.555[,.]55 is recorded as taken, and the hire is due back on 13 Mar 2026\.$/,
    )
  })
})
