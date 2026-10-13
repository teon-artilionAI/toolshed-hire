/**
 * Tests for the owner reaching the photographs of a damage report from SC-21
 * (#112), with the network replaced at `fetch`.
 *
 * A unit on the register links its open damage reports to the damage screen,
 * where the owner resolves them. There each report lists its photographs, and
 * they stay in view while the owner records the cost, so the cost can be
 * weighed against what the counter photographed.
 */

import { screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DamageReport, LocatedUnit } from '../../shared/api/contract'
import { jsonResponse } from '../../test/api-mock'
import { SHELF_UNIT } from '../../test/admin-asset-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { DAMAGE_REPORTS_ROUTE, EARLIER_REPORT, QUARANTINED_AT_BELLVILLE, reportPage } from '../../test/damage-samples'
import { LOCATOR_ROUTE, locatorPage } from '../../test/overview-samples'
import { photoList, photosOf, photosRoute, switchedOff, SWITCHED_OFF_DETAIL } from '../../test/photo-samples'
import { SCREEN_WAIT, findScreenHeading } from '../../test/render-app'
import { REGISTER, findUnit, openRegister } from './SC21-test-kit'

const TAG = SHELF_UNIT.assetTag

/** The unit of the register as the locator finds it, set aside by its damage. */
const LOCATED: LocatedUnit = { ...QUARANTINED_AT_BELLVILLE, assetTag: TAG, modelName: SHELF_UNIT.modelName }

/** An open report on that unit. */
const REPORT: DamageReport = { ...EARLIER_REPORT, assetTag: TAG, modelName: SHELF_UNIT.modelName }

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

/** Open the unit on the register and follow its open damage reports to the damage screen. */
async function followToDamage(list: () => Response) {
  const opened = await openRegister(
    {
      [LOCATOR_ROUTE]: () => jsonResponse(locatorPage([LOCATED])),
      [DAMAGE_REPORTS_ROUTE]: () => jsonResponse(reportPage([REPORT])),
      [photosRoute(REPORT.id)]: list,
    },
    `${REGISTER}?asset=${TAG}`,
  )
  const unit = await findUnit(TAG)
  await opened.user.click(within(unit).getByRole('link', { name: /^2 open damage reports, resolve on the damage screen/ }))
  await findScreenHeading('Record damage')
  const entry = await screen.findByRole('article', { name: REPORT.reference }, SCREEN_WAIT)
  return { ...opened, entry }
}

describe('the owner resolving a report reached from the register', () => {
  it('sees its photographs, and they stay in view while the cost is recorded', async () => {
    const { user, entry } = await followToDamage(() => jsonResponse(photoList(photosOf(REPORT, 3))))
    await within(entry).findByRole('list', { name: `Photographs of ${REPORT.reference}` }, SCREEN_WAIT)

    await user.click(within(entry).getByRole('button', { name: `Resolve ${REPORT.reference}` }))
    await user.click(within(entry).getByRole('radio', { name: /^Repaired/ }))

    expect(within(entry).getByLabelText('Actual repair cost, in rand')).toBeVisible()
    expect(within(entry).getAllByRole('button', { name: /^Photograph \d of/ })).toHaveLength(3)
  })

  it('is told in plain words when photographs are switched off', async () => {
    const { entry } = await followToDamage(switchedOff)

    expect(await within(entry).findByText(SWITCHED_OFF_DETAIL, {}, SCREEN_WAIT)).toBeVisible()
    expect(within(entry).queryByLabelText(/^Add a photograph/)).not.toBeInTheDocument()
    expect(within(entry).getByRole('button', { name: `Resolve ${REPORT.reference}` })).toBeVisible()
  })
})
