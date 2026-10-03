/**
 * What the SC-16 test files share.
 *
 * The damage screen is opened inside the whole application, by default as the
 * counter assistant at Bellville, with the clock pinned to `TEST_NOW`. The
 * unit is found through the locator route, its reports through the damage
 * route, and the hire it came back on through the rental route, and each test
 * says how those and the writes answer.
 */

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import type { DamageReport, LocatedUnit, SessionUser } from '../../shared/api/contract'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteTable } from '../../test/api-mock'
import { DAMAGE_REPORTS_ROUTE, reportPage } from '../../test/damage-samples'
import { LOCATOR_ROUTE, locatorPage } from '../../test/overview-samples'
import { SCREEN_WAIT, findScreenHeading, renderApp } from '../../test/render-app'
import { WAITING_FOR_DAMAGE, rentalRoute } from '../../test/rental-samples'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'

export const HEADING = 'Record damage'
export const ASK = 'Record the damage and quarantine the unit'
export const ANSWER = 'Yes, file the report'
export const CHARGEABLE = 'Is the customer charged for this damage?'
export const RECOVERY = 'Amount to recover from the customer, in rand, including VAT'

/** Routes in which the locator finds this unit, these reports are on it, and
 *  the hire it came back on is waiting for its report. */
export function unitWith(unit: LocatedUnit, reports: DamageReport[] = [], routes: RouteTable = {}): RouteTable {
  return {
    [LOCATOR_ROUTE]: () => jsonResponse(locatorPage([unit])),
    [DAMAGE_REPORTS_ROUTE]: () => jsonResponse(reportPage(reports)),
    [rentalRoute()]: () => jsonResponse(WAITING_FOR_DAMAGE),
    ...routes,
  }
}

/** Open SC-16 at this address, with these routes answering. */
export async function openDamage(
  routes: RouteTable,
  at: string,
  account: SessionUser = COUNTER_STAFF,
): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(account), ...routes })
  renderApp(at)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/** Wait for the form, which is only there once the unit is found. */
export function findForm(): Promise<HTMLElement> {
  return screen.findByRole('form', { name: 'What happened' }, SCREEN_WAIT)
}

/** What a test records on the form. Anything left out is left as it opens. */
export interface Answers {
  severity?: string
  description?: string
  estimate?: string
  charge?: 'Charge the customer' | 'Do not charge the customer'
  recovery?: string
}

/** Fill the form the way an assistant would. */
export async function answer(user: UserEvent, answers: Answers): Promise<void> {
  const form = await findForm()
  if (answers.severity) {
    await user.click(within(within(form).getByRole('group', { name: 'How bad is it' })).getByRole('radio', { name: new RegExp(`^${answers.severity}`) }))
  }
  if (answers.description) await user.type(within(form).getByLabelText('Describe the damage'), answers.description)
  if (answers.estimate) await user.type(within(form).getByLabelText('Estimated repair cost, in rand'), answers.estimate)
  if (answers.charge) {
    await user.click(within(within(form).getByRole('group', { name: CHARGEABLE })).getByRole('radio', { name: new RegExp(`^${answers.charge}`) }))
  }
  if (answers.recovery) await user.type(within(form).getByLabelText(RECOVERY), answers.recovery)
}

/** A form with everything a report needs, charging the customer when asked. */
export const COMPLETE: Answers = {
  severity: 'Major',
  description: 'Base plate cracked across the weld.',
  estimate: '456.78',
  charge: 'Charge the customer',
  recovery: '321.09',
}
