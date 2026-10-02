/**
 * Tests for correcting the profile on SC-09, with the network replaced at
 * `fetch`.
 *
 * The form holds the fields the API lets a customer change. What these tests
 * hold it to is that it sends only what was changed, once, that it shows the
 * profile the server answered with, and that a refusal lands under the field
 * it names.
 */

import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PROFILE, PROFILE_UPDATE_ROUTE, refusedFields } from '../../test/account-samples'
import { jsonResponse } from '../../test/api-mock'
import type { MyProfile } from '../../shared/api/contract'
import { SAVED_TITLE, detail, openAccount, startEditing, withProfile } from './SC09-test-kit'

describe('editing the profile', () => {
  it('opens a form holding what the server holds, for the fields a customer may change', async () => {
    const { user } = await openAccount(withProfile(PROFILE))

    await startEditing(user)

    expect(screen.getByLabelText('Full name')).toHaveValue('Wesley Adonis')
    expect(screen.getByLabelText('Mobile number')).toHaveValue('0824417719')
    expect(screen.getByLabelText('Company name')).toHaveValue('')
    expect(screen.getByLabelText('VAT number')).toHaveValue('')
    expect(screen.getByLabelText('Billing address, first line')).toHaveValue('12 Loop Street')
    expect(screen.getByLabelText('Billing suburb')).toHaveValue('Gardens')
    expect(screen.getByLabelText('Billing city')).toHaveValue('Cape Town')
    expect(screen.getByLabelText('Postal code')).toHaveValue('8001')
    expect(screen.getAllByRole('textbox')).toHaveLength(8)
  })

  it('sends only what was changed, once, and shows the profile the server answered with', async () => {
    const updated: MyProfile = { ...PROFILE, phone: '0835550199', billingSuburb: 'Salt River' }
    const { user, network } = await openAccount(
      withProfile(PROFILE, { [PROFILE_UPDATE_ROUTE]: () => jsonResponse(updated) }),
    )
    await startEditing(user)
    await user.clear(screen.getByLabelText('Mobile number'))
    await user.type(screen.getByLabelText('Mobile number'), '083 555 0199')
    await user.clear(screen.getByLabelText('Billing suburb'))
    await user.type(screen.getByLabelText('Billing suburb'), 'Salt River')

    await user.click(screen.getByRole('button', { name: 'Save these details' }))

    const saved = await screen.findByText(SAVED_TITLE)
    expect(saved).toBeVisible()
    await waitFor(() => expect(saved.closest('[tabindex="-1"]')).toHaveFocus())
    const calls = network.requestsTo(PROFILE_UPDATE_ROUTE)
    expect(calls).toHaveLength(1)
    expect(calls[0].body).toEqual({ phone: '0835550199', billingSuburb: 'Salt River' })
    expect(detail('Mobile number')).toHaveTextContent('0835550199')
    expect(detail('Billing address')).toHaveTextContent('12 Loop Street, Salt River, Cape Town, 8001')
    expect(screen.queryByLabelText('Mobile number')).not.toBeInTheDocument()
  })

  it('sends an emptied company name as null and a new one as text', async () => {
    const trade: MyProfile = { ...PROFILE, companyName: 'Old Name', vatNumber: '4123456789' }
    const { user, network } = await openAccount(
      withProfile(trade, { [PROFILE_UPDATE_ROUTE]: () => jsonResponse({ ...trade, companyName: 'New Name', vatNumber: null }) }),
    )
    await startEditing(user)
    await user.clear(screen.getByLabelText('Company name'))
    await user.type(screen.getByLabelText('Company name'), 'New Name')
    await user.clear(screen.getByLabelText('VAT number'))

    await user.click(screen.getByRole('button', { name: 'Save these details' }))

    await screen.findByText(SAVED_TITLE)
    expect(network.requestsTo(PROFILE_UPDATE_ROUTE)[0].body).toEqual({ companyName: 'New Name', vatNumber: null })
    expect(screen.queryByText('VAT number', { selector: 'dt' })).not.toBeInTheDocument()
  })

  it('sends nothing when nothing was changed, and says so', async () => {
    const { user, network } = await openAccount(withProfile(PROFILE))
    await startEditing(user)

    await user.click(screen.getByRole('button', { name: 'Save these details' }))

    expect(await screen.findByText('Nothing was changed')).toBeVisible()
    expect(network.requestsTo(PROFILE_UPDATE_ROUTE)).toHaveLength(0)
  })

  it('checks what was changed before it asks the API, and says why beside the field', async () => {
    const { user, network } = await openAccount(withProfile(PROFILE))
    await startEditing(user)
    await user.clear(screen.getByLabelText('Mobile number'))
    await user.type(screen.getByLabelText('Mobile number'), '12345')
    await user.clear(screen.getByLabelText('Postal code'))

    await user.click(screen.getByRole('button', { name: 'Save these details' }))

    const phone = screen.getByLabelText('Mobile number')
    expect(phone).toBeInvalid()
    expect(phone).toHaveAccessibleDescription(/Enter ten digits starting with a zero/)
    expect(screen.getByLabelText('Postal code')).toHaveAccessibleDescription(/Enter the postal code/)
    expect(network.requestsTo(PROFILE_UPDATE_ROUTE)).toHaveLength(0)
  })

  it('puts each message of a 422 under the field it names, and lists any other', async () => {
    const { user, network } = await openAccount(
      withProfile(PROFILE, {
        [PROFILE_UPDATE_ROUTE]: () =>
          refusedFields({
            phone: 'That number is not in service.',
            accountStatus: 'This field cannot be changed.',
          }),
      }),
    )
    await startEditing(user)
    await user.clear(screen.getByLabelText('Mobile number'))
    await user.type(screen.getByLabelText('Mobile number'), '0835550199')

    await user.click(screen.getByRole('button', { name: 'Save these details' }))

    const phone = screen.getByLabelText('Mobile number')
    await waitFor(() => expect(phone).toHaveAccessibleDescription(/That number is not in service\./))
    expect(phone).toBeInvalid()
    expect(screen.getByRole('alert')).toHaveTextContent('This field cannot be changed.')
    expect(screen.queryByText(SAVED_TITLE)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save these details' })).toBeEnabled()

    network.setRoute(PROFILE_UPDATE_ROUTE, () => jsonResponse({ ...PROFILE, phone: '0835550188' }))
    await user.type(phone, '{Backspace}{Backspace}88')
    expect(phone).not.toHaveAccessibleDescription(/not in service/)
    await user.click(screen.getByRole('button', { name: 'Save these details' }))

    expect(await screen.findByText(SAVED_TITLE)).toBeVisible()
    expect(network.requestsTo(PROFILE_UPDATE_ROUTE)[1].body).toEqual({ phone: '0835550188' })
  })

  it('shows the shared error state when the save cannot reach the API, and keeps the form', async () => {
    const { user } = await openAccount(
      withProfile(PROFILE, {
        [PROFILE_UPDATE_ROUTE]: () => {
          throw new TypeError('Failed to fetch')
        },
      }),
    )
    await startEditing(user)
    await user.type(screen.getByLabelText('Billing suburb'), ' East')

    await user.click(screen.getByRole('button', { name: 'Save these details' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('We could not save your details')
    expect(screen.getByLabelText('Billing suburb')).toHaveValue('Gardens East')
  })

  it('discards the changes on request and puts focus back on the edit button', async () => {
    const { user, network } = await openAccount(withProfile(PROFILE))
    await startEditing(user)
    await user.type(screen.getByLabelText('Billing suburb'), ' East')

    await user.click(screen.getByRole('button', { name: 'Discard the changes' }))

    expect(detail('Billing address')).toHaveTextContent('12 Loop Street, Gardens, Cape Town, 8001')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Edit my details' })).toHaveFocus())
    expect(network.requestsTo(PROFILE_UPDATE_ROUTE)).toHaveLength(0)
  })
})
