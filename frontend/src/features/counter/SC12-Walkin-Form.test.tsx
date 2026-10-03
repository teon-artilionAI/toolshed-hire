/**
 * Tests for the walk in form on SC-12, with the network replaced at `fetch`.
 *
 * The form is filled in the way an assistant would, and each test says how
 * the walk in route answers. What these hold the screen to is that it sends
 * exactly what the contract asks for, once, never the whole document number,
 * ties every problem to its field, and chooses the new customer once the
 * server has registered them. An administrator, who has no branch, chooses one
 * first and the walk in names it.
 */

import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { createdResponse, neverAnswers, problemResponse } from '../../test/api-mock'
import { CUSTOMER_ID, REGISTER_WALK_IN_ROUTE, THANDI } from '../../test/counter-samples'
import { SCREEN_WAIT, currentAddress } from '../../test/render-app'
import { ADMIN } from '../../test/session-samples'
import { WORK_BRANCH_STORAGE_KEY } from './work-branch-storage'
import { ADD_CUSTOMER, CHOSEN_READS, fillInWalkIn, openLookup } from './SC12-test-kit'

const WALK_IN_BODY = {
  displayName: 'Thandi Mokoena',
  phone: '0824417719',
  idDocumentType: 'SA_ID',
  idDocumentLast4: '5083',
  billingAddressLine1: '12 Loop Street',
  billingSuburb: 'Gardens',
  billingCity: 'Cape Town',
  billingPostalCode: '8001',
  customerType: 'INDIVIDUAL',
  companyName: null,
  vatNumber: null,
  branchCode: null,
}

describe('the walk in form', () => {
  it('asks for the last four characters of the document and never the whole number', async () => {
    await openLookup(CHOSEN_READS)

    const lastFour = screen.getByLabelText('Last four characters of the document number')
    expect(lastFour).toHaveAttribute('maxlength', '4')
    expect(lastFour).toHaveAccessibleDescription(/The whole number is never kept/)
    expect(screen.queryByLabelText(/Document number$/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument()
  })

  it('checks every answer before it asks the API, and ties each problem to its field', async () => {
    const { user, network } = await openLookup(CHOSEN_READS)

    await user.click(screen.getByRole('button', { name: ADD_CUSTOMER }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('This customer has not been added yet. 6 answers need fixing.')
    expect(within(alert).getByRole('link', { name: /full name/ })).toHaveAttribute('href', '#walkin-displayName')
    expect(screen.getByLabelText('Full name')).toBeInvalid()
    expect(screen.getByLabelText('Full name')).toHaveAccessibleDescription(/full name as it appears/)
    expect(screen.getByLabelText('Mobile number')).toHaveAccessibleDescription(/mobile number is needed/)
    expect(screen.getByLabelText('Postal code')).toHaveAccessibleDescription(/postal code/)
    expect(network.requestsTo(REGISTER_WALK_IN_ROUTE)).toHaveLength(0)
  })

  it('asks for the company only for a trade account', async () => {
    const { user } = await openLookup(CHOSEN_READS)
    expect(screen.queryByLabelText('Company name')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Kind of customer'), 'Trade account')
    await user.click(screen.getByRole('button', { name: ADD_CUSTOMER }))

    expect(screen.getByLabelText('Company name')).toHaveAccessibleDescription(/needs the name of the company/)
  })
})

describe('sending a walk in', () => {
  it('sends exactly what the contract asks for, once, and chooses the new customer', async () => {
    const { user, network } = await openLookup({
      ...CHOSEN_READS,
      [REGISTER_WALK_IN_ROUTE]: () => createdResponse(THANDI),
    })
    await fillInWalkIn(user)

    await user.click(screen.getByRole('button', { name: ADD_CUSTOMER }))

    const heading = await screen.findByRole('heading', { level: 2, name: THANDI.displayName }, SCREEN_WAIT)
    await waitFor(() => expect(heading).toHaveFocus())
    expect(network.requestsTo(REGISTER_WALK_IN_ROUTE)).toHaveLength(1)
    expect(network.requestsTo(REGISTER_WALK_IN_ROUTE)[0].body).toEqual(WALK_IN_BODY)
    expect(screen.getByText(`${THANDI.displayName} is on file`)).toBeVisible()
    expect(screen.getByRole('link', { name: `New booking for ${THANDI.displayName}` })).toHaveAttribute(
      'href',
      `/counter/booking?customer=${CUSTOMER_ID}`,
    )
    expect(currentAddress()).toBe(`/counter/customers?customer=${CUSTOMER_ID}`)
    // The form is empty again, ready for the next customer in the queue.
    expect(screen.getByLabelText('Full name')).toHaveValue('')
  })

  it('disables the button while the request is in flight, so it cannot be sent twice', async () => {
    const { user, network } = await openLookup({ ...CHOSEN_READS, [REGISTER_WALK_IN_ROUTE]: neverAnswers })
    await fillInWalkIn(user)

    await user.click(screen.getByRole('button', { name: ADD_CUSTOMER }))

    const button = await screen.findByRole('button', { name: 'Adding the customer' })
    expect(button).toBeDisabled()
    expect(screen.getByText('Adding the customer, please wait')).toBeInTheDocument()
    await user.click(button)
    expect(network.requestsTo(REGISTER_WALK_IN_ROUTE)).toHaveLength(1)
  })

  it('puts each refusal from the API under the field it names, and lists the rest', async () => {
    const { user } = await openLookup({
      ...CHOSEN_READS,
      [REGISTER_WALK_IN_ROUTE]: () =>
        problemResponse(422, {
          detail: 'Two fields were refused.',
          errors: {
            fields: {
              'body.phone': 'This number is already on file for another customer.',
              'body.homeBranchCode': 'The branch is not trading.',
            },
          },
        }),
    })
    await fillInWalkIn(user)

    await user.click(screen.getByRole('button', { name: ADD_CUSTOMER }))

    const phone = screen.getByLabelText('Mobile number')
    await waitFor(() => expect(phone).toHaveAccessibleDescription('This number is already on file for another customer.'))
    expect(phone).toBeInvalid()
    expect(screen.getByText('The branch is not trading.')).toBeVisible()

    // Changing the field takes the server's sentence away.
    await user.type(phone, '0')
    expect(phone).not.toHaveAccessibleDescription(/already on file/)
  })

  it('says so when the walk in fails some other way, and keeps what was typed', async () => {
    const { user } = await openLookup({ ...CHOSEN_READS, [REGISTER_WALK_IN_ROUTE]: () => problemResponse(500) })
    await fillInWalkIn(user)

    await user.click(screen.getByRole('button', { name: ADD_CUSTOMER }))

    expect(await screen.findByRole('alert')).toHaveTextContent('We could not add the customer')
    expect(screen.getByLabelText('Full name')).toHaveValue('Thandi Mokoena')
  })
})

describe('an administrator at the counter', () => {
  it('chooses a branch first, keeps it for the tab, and registers the walk in there', async () => {
    const { user, network } = await openLookup(
      { ...CHOSEN_READS, [REGISTER_WALK_IN_ROUTE]: () => createdResponse(THANDI) },
      ADMIN,
    )
    expect(screen.queryByLabelText('Search customers')).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: /Somerset West/ }, SCREEN_WAIT))

    expect(await screen.findByText(/You are working at/)).toHaveTextContent('You are working at Somerset West in this tab.')
    expect(window.sessionStorage.getItem(WORK_BRANCH_STORAGE_KEY)).toBe('SMW')
    await fillInWalkIn(user)
    await user.click(screen.getByRole('button', { name: ADD_CUSTOMER }))

    await screen.findByRole('heading', { level: 2, name: THANDI.displayName }, SCREEN_WAIT)
    expect(network.requestsTo(REGISTER_WALK_IN_ROUTE)[0].body).toMatchObject({ branchCode: 'SMW' })
  })
})
