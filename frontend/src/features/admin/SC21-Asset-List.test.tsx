/**
 * Tests for the register on SC-21, with the network replaced at `fetch`.
 *
 * The register is one paged read with a search and three filters. Waiting,
 * failed, empty and loaded, every value as the server sent it, the search and
 * the filters in the address and in the query, the model found by searching,
 * a refusal under its control, and paging.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { formatDate } from '../../shared/format'
import { SAMPLE_DATA_TITLE } from '../../shared/sample-data-notice'
import { jsonResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { HAMMER, MODELS_ROUTE } from '../../test/admin-catalogue-samples'
import { ASSETS_ROUTE, INTAKE_UNIT, RETIRED_UNIT, SHELF_UNIT, assetPage } from '../../test/admin-asset-samples'
import { TEST_NOW } from '../../test/catalogue-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { REGISTER, findUnits, lastAsked, openRegister, rowOf, unitsRegion } from './SC21-test-kit'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'], now: TEST_NOW })
})

describe('reading the register', () => {
  it('is connected, and shows every unit as the server sent it', async () => {
    const { network } = await openRegister()
    await findUnits()

    expect(screen.queryByText(SAMPLE_DATA_TITLE)).not.toBeInTheDocument()
    expect(lastAsked(network, ASSETS_ROUTE).toString()).toBe('page=1&pageSize=20')
    expect(within(unitsRegion()).getByText('3 units match, in tag order.')).toBeVisible()

    const shelf = await rowOf(SHELF_UNIT.assetTag)
    expect(within(shelf).getByText('Serial GBH-778812')).toBeVisible()
    expect(within(shelf).getByText(SHELF_UNIT.modelName)).toBeVisible()
    expect(within(shelf).getByText(SHELF_UNIT.categoryName)).toBeVisible()
    expect(within(shelf).getByText('Bellville')).toBeVisible()
    expect(within(shelf).getByText('On the shelf', { selector: '.pill' })).toBeVisible()
    expect(within(shelf).getByText('B, good working order')).toBeVisible()
    const reports = within(shelf).getByRole('link', { name: `2 open reports on ${SHELF_UNIT.assetTag}` })
    expect(reports).toHaveAttribute('href', `/counter/damage/${SHELF_UNIT.assetTag}`)
    expect(within(shelf).getByRole('link', { name: `Open ${SHELF_UNIT.assetTag}` })).toHaveAttribute(
      'href',
      `${REGISTER}?asset=${SHELF_UNIT.assetTag}`,
    )

    const intake = await rowOf(INTAKE_UNIT.assetTag)
    expect(within(intake).getByText('Being booked in, not hireable yet', { selector: '.pill' })).toBeVisible()
    expect(within(intake).getByText('None')).toBeVisible()

    const retired = await rowOf(RETIRED_UNIT.assetTag)
    expect(within(retired).getByText('Retired from the fleet', { selector: '.pill' })).toBeVisible()
    expect(within(retired).getByText(`Since ${formatDate('2026-02-28')}`)).toBeVisible()
  })

  it('draws a skeleton while it loads', async () => {
    await openRegister({ [ASSETS_ROUTE]: neverAnswers })

    expect(await within(unitsRegion()).findByText('Loading the units.', {}, SCREEN_WAIT)).toBeInTheDocument()
    expect(unitsRegion().querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('says so with the reference when it cannot be read, and reads it again on a retry', async () => {
    const { user, network } = await openRegister({ [ASSETS_ROUTE]: () => problemResponse(500, { requestId: 'req-assets-1' }) })

    const alert = await within(unitsRegion()).findByRole('alert', {}, SCREEN_WAIT)
    expect(alert).toHaveTextContent('We could not load the register')
    expect(within(alert).getByText('req-assets-1')).toBeVisible()

    network.setRoute(ASSETS_ROUTE, () => jsonResponse(assetPage([SHELF_UNIT])))
    await user.click(within(alert).getByRole('button', { name: 'Try again' }))
    expect(await rowOf(SHELF_UNIT.assetTag)).toBeVisible()
  })

  it('offers to register the first unit when the register is empty', async () => {
    const { user } = await openRegister({ [ASSETS_ROUTE]: () => jsonResponse(assetPage([])) })

    expect(await screen.findByText('The register has no units yet', {}, SCREEN_WAIT)).toBeVisible()
    await user.click(within(unitsRegion()).getByRole('button', { name: 'Register a unit' }))

    await waitFor(() => expect(currentAddress()).toBe(`${REGISTER}?add=unit`))
    expect(await screen.findByRole('heading', { level: 2, name: 'Register a unit' }, SCREEN_WAIT)).toHaveFocus()
  })

  it('says so when nothing matches, and clears the filters', async () => {
    const { user, network } = await openRegister(
      { [ASSETS_ROUTE]: () => jsonResponse(assetPage([])) },
      `${REGISTER}?q=chipper&status=LOST`,
    )

    expect(await screen.findByText('No unit matches', {}, SCREEN_WAIT)).toBeVisible()
    expect(lastAsked(network, ASSETS_ROUTE).toString()).toBe('q=chipper&status=LOST&page=1&pageSize=20')
    await user.click(screen.getByRole('button', { name: 'Clear the filters' }))

    await waitFor(() => expect(currentAddress()).toBe(REGISTER))
    await waitFor(() => expect(lastAsked(network, ASSETS_ROUTE).toString()).toBe('page=1&pageSize=20'))
  })
})

describe('the search, the filters and the pages', () => {
  it('searches a moment after the last key and keeps the search in the address', async () => {
    const { user, network } = await openRegister()
    await findUnits()

    await user.type(screen.getByLabelText('Search by tag, serial number or model'), '0042')

    await waitFor(() => expect(lastAsked(network, ASSETS_ROUTE).get('q')).toBe('0042'), SCREEN_WAIT)
    expect(currentAddress()).toBe(`${REGISTER}?q=0042`)
    expect(network.requestsTo(ASSETS_ROUTE).filter((request) => request.query.has('q'))).toHaveLength(1)
  })

  it('narrows to one branch and one status as they are chosen, each status in words', async () => {
    const { user, network } = await openRegister()
    await findUnits()

    await user.selectOptions(screen.getByLabelText('Branch'), 'BLV')
    await waitFor(() => expect(lastAsked(network, ASSETS_ROUTE).get('branchCode')).toBe('BLV'))

    const status = screen.getByLabelText('Status')
    expect(within(status).getByRole('option', { name: 'In the workshop' })).toBeInTheDocument()
    await user.selectOptions(status, 'UNDER_REPAIR')

    await waitFor(() => expect(lastAsked(network, ASSETS_ROUTE).get('status')).toBe('UNDER_REPAIR'))
    expect(currentAddress()).toBe(`${REGISTER}?branchCode=BLV&status=UNDER_REPAIR`)
  })

  it('finds a model by searching for it, and narrows the register to its units', async () => {
    const { user, network } = await openRegister()
    await findUnits()
    const menu = screen.getByLabelText('Model to show')
    expect(menu).toHaveAccessibleDescription(expect.stringContaining('Type two characters or more'))

    await user.type(screen.getByLabelText('Find a model by name or stock code'), 'bosch')

    await waitFor(() => expect(lastAsked(network, MODELS_ROUTE).toString()).toBe('q=bosch&page=1&pageSize=20'), SCREEN_WAIT)
    await waitFor(() => expect(menu).toHaveAccessibleDescription('2 models match.'))
    await user.selectOptions(menu, `${HAMMER.name} (${HAMMER.sku})`)

    await waitFor(() => expect(lastAsked(network, ASSETS_ROUTE).get('modelId')).toBe(HAMMER.id))
    expect(currentAddress()).toBe(`${REGISTER}?modelId=${HAMMER.id}`)
  })

  it('names the model the address narrows to, from its own read', async () => {
    await openRegister({}, `${REGISTER}?modelId=${HAMMER.id}`)
    await findUnits()

    await waitFor(() => expect(screen.getByLabelText('Model to show')).toHaveDisplayValue(HAMMER.name))
  })

  it('asks for another page, keeps it in the address and moves focus to the top of the units', async () => {
    const { user, network } = await openRegister({ [ASSETS_ROUTE]: () => jsonResponse(assetPage([SHELF_UNIT], { total: 41 })) })
    await findUnits()

    await user.click(screen.getByRole('button', { name: 'Page 3' }))

    await waitFor(() => expect(lastAsked(network, ASSETS_ROUTE).get('page')).toBe('3'))
    expect(currentAddress()).toBe(`${REGISTER}?page=3`)
    expect(unitsRegion()).toHaveFocus()
  })

  it('puts a refusal under the control it names and lists any other', async () => {
    await openRegister(
      {
        [ASSETS_ROUTE]: () =>
          problemResponse(422, {
            errors: { fields: { 'query.branchCode': 'No branch has that code.', 'query.pageSize': 'Ask for 100 at most.' } },
          }),
      },
      `${REGISTER}?branchCode=XYZ`,
    )

    expect(await screen.findByText('The register cannot be read with those filters', {}, SCREEN_WAIT)).toBeVisible()
    expect(screen.getByLabelText('Branch')).toHaveAccessibleDescription('No branch has that code.')
    expect(screen.getByText('Ask for 100 at most.')).toBeVisible()
  })
})
