/**
 * Tests for SC-16 Damage Report Capture as it opens, with the network replaced
 * at `fetch`.
 *
 * The unit is found through the locator by the tag in the address, so the
 * screen has a loading, a failed, a not found and a loaded state, and the
 * reports on the unit have their own. The form opens with no decision on
 * charging, says beside it that fair wear and tear is not charged, and sends
 * nothing until every answer is there. The writes are in
 * SC16-Damage-Writes.test.tsx and the owner's moves in SC16-Resolution.test.tsx.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { TEST_NOW } from '../../test/catalogue-samples'
import {
  DAMAGED_ITEM,
  DAMAGE_REPORTS_ROUTE,
  EARLIER_REPORT,
  FILED_ON_THE_HIRE,
  FILE_DAMAGE_ROUTE,
  HELD_AT_CBD,
  ON_THE_SHELF,
  QUARANTINED_AT_BELLVILLE,
  RESOLVED_REPORT,
  reportPage,
} from '../../test/damage-samples'
import { LOCATOR_ROUTE, locatorPage } from '../../test/overview-samples'
import { SCREEN_WAIT } from '../../test/render-app'
import { ASK, CHARGEABLE, RECOVERY, answer, findForm, openDamage, unitWith } from './SC16-test-kit'

const ON_THE_HIRE = `/counter/damage/${QUARANTINED_AT_BELLVILLE.assetTag}?rentalItem=${DAMAGED_ITEM.id}`
const OFF_HIRE = `/counter/damage/${ON_THE_SHELF.assetTag}`

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('finding the unit', () => {
  it('says it is finding the unit while the locator answers', async () => {
    await openDamage({ [LOCATOR_ROUTE]: neverAnswers }, OFF_HIRE)

    expect(await screen.findByText('Finding the unit', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
  })

  it('asks the locator for the tag, and shows the unit, where it is and its state, connected', async () => {
    const { network } = await openDamage(unitWith(QUARANTINED_AT_BELLVILLE), ON_THE_HIRE)
    await findForm()

    expect(network.requestsTo(LOCATOR_ROUTE)[0].query.get('q')).toBe('TSH-PC-0007')
    expect(screen.getByText('TSH-PC-0007, CP 100 Plate Compactor, at Bellville.')).toBeVisible()
    expect(screen.getByText('Quarantined until inspected')).toBeVisible()
    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(screen.getByText('This unit came back on a hire')).toBeVisible()
  })

  it('says so with the reference when the locator fails, and asks again on a retry', async () => {
    const { user, network } = await openDamage(
      { [LOCATOR_ROUTE]: () => problemResponse(500, { requestId: 'req-damage-1' }) },
      OFF_HIRE,
    )

    const alert = await screen.findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load this unit')
    expect(within(alert).getByText('req-damage-1')).toBeVisible()

    network.setRoute(LOCATOR_ROUTE, () => jsonResponse(locatorPage([ON_THE_SHELF])))
    network.setRoute(DAMAGE_REPORTS_ROUTE, () => jsonResponse(reportPage([])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))

    expect(await findForm()).toBeVisible()
  })

  it.each([
    ['the locator finds only other units', `/counter/damage/TSH-PC-000`],
    ['the tag is too short to search for', '/counter/damage/T'],
  ])('says no unit has the tag when %s', async (_, at) => {
    await openDamage({ [LOCATOR_ROUTE]: () => jsonResponse(locatorPage([ON_THE_SHELF])) }, at)

    expect(await screen.findByText(/^No unit has the tag/, {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open the asset locator' })).toHaveAttribute('href', '/counter/locator')
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
  })

  it('warns a counter assistant that a unit held at another branch is filed there', async () => {
    await openDamage(unitWith(HELD_AT_CBD), `/counter/damage/${HELD_AT_CBD.assetTag}`)
    await findForm()

    expect(screen.getByText('TSH-PC-0021 is held at Cape Town CBD')).toBeVisible()
  })
})

describe('the reports already on the unit', () => {
  it('lists them newest first with their status in words, from the damage route for the tag', async () => {
    const { network } = await openDamage(unitWith(QUARANTINED_AT_BELLVILLE, [EARLIER_REPORT, RESOLVED_REPORT]), ON_THE_HIRE)

    const list = await screen.findByRole('list', { name: 'Damage reports on TSH-PC-0007' }, SCREEN_WAIT)
    const [first, second] = within(list).getAllByRole('article')
    expect(first).toHaveAccessibleName(EARLIER_REPORT.reference)
    expect(within(first).getByText('Open, unit in quarantine')).toBeVisible()
    expect(within(first).getByText(EARLIER_REPORT.description)).toBeVisible()
    expect(within(first).getByText(/Repair estimated at R\s123[,.]45\. The customer was not charged\./)).toBeVisible()
    expect(within(second).getByText('Resolved, repaired')).toBeVisible()
    expect(within(second).getByText(/The repair cost R\s98[,.]76\. New grip fitted\./)).toBeVisible()
    expect(network.requestsTo(DAMAGE_REPORTS_ROUTE)[0].query.toString()).toBe('assetTag=TSH-PC-0007&page=1&pageSize=20')
  })

  it('says when there are none', async () => {
    await openDamage(unitWith(ON_THE_SHELF), OFF_HIRE)

    expect(await screen.findByText('Nothing has been reported against TSH-PC-0011 before.', {}, SCREEN_WAIT)).toBeVisible()
  })

  it('says so when they cannot be read, and the form still works', async () => {
    await openDamage(
      { ...unitWith(ON_THE_SHELF), [DAMAGE_REPORTS_ROUTE]: () => problemResponse(500) },
      OFF_HIRE,
    )

    expect(await screen.findByText('We could not load the damage reports of this unit', {}, SCREEN_WAIT)).toBeVisible()
    expect(await findForm()).toBeVisible()
  })
})

describe('the form', () => {
  it('opens with no decision on charging, and says beside it that fair wear and tear is not charged', async () => {
    await openDamage(unitWith(QUARANTINED_AT_BELLVILLE), ON_THE_HIRE)
    const form = await findForm()

    const decision = within(form).getByRole('group', { name: CHARGEABLE })
    const choices = within(decision).getAllByRole('radio')
    expect(choices).toHaveLength(2)
    for (const choice of choices) expect(choice).not.toBeChecked()
    expect(decision).toHaveAccessibleDescription(/^Fair wear and tear is not charged\./)
    expect(within(form).queryByLabelText(RECOVERY)).not.toBeInTheDocument()
    expect(within(form).queryByText(/photograph/i)).not.toBeInTheDocument()
  })

  it('refuses to send a form with no decision on charging, and ties each problem to its field', async () => {
    const { user, network } = await openDamage(unitWith(QUARANTINED_AT_BELLVILLE), ON_THE_HIRE)
    await answer(user, { severity: 'Minor', description: 'Dent in the guard.', estimate: '50' })

    await user.click(screen.getByRole('button', { name: ASK }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Nothing has been filed yet. 1 answer needs fixing.')
    expect(screen.getByRole('group', { name: CHARGEABLE })).toHaveAccessibleDescription(/Neither answer is chosen for you\.$/)
    expect(within(alert).getByRole('link', { name: /Choose whether the customer is charged/ })).toHaveAttribute('href', '#damage-chargeable')
    expect(screen.queryByRole('heading', { level: 2, name: /^File this damage report/ })).not.toBeInTheDocument()
    expect(network.requestsTo(FILE_DAMAGE_ROUTE)).toHaveLength(0)
  })

  it('holds back every missing answer, each under its own field', async () => {
    const { user } = await openDamage(unitWith(QUARANTINED_AT_BELLVILLE), ON_THE_HIRE)
    await findForm()

    await user.click(screen.getByRole('button', { name: ASK }))

    expect(await screen.findByRole('alert')).toHaveTextContent('4 answers need fixing.')
    expect(screen.getByRole('group', { name: 'How bad is it' })).toHaveAccessibleDescription('Choose how bad the damage is.')
    expect(screen.getByLabelText('Describe the damage')).toHaveAccessibleDescription(/Describe what is broken\./)
    expect(screen.getByLabelText('Estimated repair cost, in rand')).toHaveAccessibleDescription(/Enter the estimated repair cost/)
  })

  it('asks for the amount to recover only when the customer is charged on a hire', async () => {
    const { user } = await openDamage(unitWith(QUARANTINED_AT_BELLVILLE), ON_THE_HIRE)
    await answer(user, { charge: 'Charge the customer' })

    expect(screen.getByLabelText(RECOVERY)).toHaveAccessibleDescription(/may not be more than the replacement value/)
    await answer(user, { charge: 'Do not charge the customer' })
    expect(screen.queryByLabelText(RECOVERY)).not.toBeInTheDocument()
  })

  it('names the replacement value when an earlier report on the same hire of the unit gave it', async () => {
    const { user } = await openDamage(unitWith(QUARANTINED_AT_BELLVILLE, [FILED_ON_THE_HIRE]), ON_THE_HIRE)
    await answer(user, { charge: 'Charge the customer' })

    await waitFor(() =>
      expect(screen.getByLabelText(RECOVERY)).toHaveAccessibleDescription(/replacement value of R\s9\s876[,.]54/),
    )
  })

  it('never asks for an amount outside a hire, where nothing is charged to a deposit', async () => {
    const { user } = await openDamage(unitWith(ON_THE_SHELF), OFF_HIRE)
    await answer(user, { charge: 'Charge the customer' })

    expect(screen.queryByLabelText(RECOVERY)).not.toBeInTheDocument()
    expect(screen.queryByText('This unit came back on a hire')).not.toBeInTheDocument()
  })
})
