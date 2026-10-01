/**
 * Tests for the shared interface primitives.
 *
 * I query the way a person or a screen reader finds things, by role, label
 * and visible text. Nothing here looks at a class name, so the styling can
 * change without a test noticing.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { DataTable, EmptyState, Field, Notice, PageHeader, StatusPill } from './ui'

describe('StatusPill', () => {
  it('shows the status as words, so it does not rely on colour', () => {
    render(<StatusPill status="ON_HIRE" />)

    expect(screen.getByText('On Hire')).toBeVisible()
  })

  it('tells apart two statuses that share a colour', () => {
    // Reserved and Maintenance are both drawn in the same tone. Only the
    // text separates them, which is the point of rendering it.
    render(
      <>
        <StatusPill status="RESERVED" />
        <StatusPill status="MAINTENANCE" />
      </>,
    )

    expect(screen.getByText('Reserved')).toBeVisible()
    expect(screen.getByText('Maintenance')).toBeVisible()
  })

  it('still shows text for a status it has never heard of', () => {
    render(<StatusPill status="AWAITING_PARTS" />)

    expect(screen.getByText('Awaiting Parts')).toBeVisible()
  })

  it('prefers a label written for the screen over the raw status', () => {
    render(<StatusPill status="OVERDUE" label="3 days late" />)

    expect(screen.getByText('3 days late')).toBeVisible()
    expect(screen.queryByText('Overdue')).not.toBeInTheDocument()
  })

  it('renders the label as its only text', () => {
    const { container } = render(<StatusPill status="AVAILABLE" />)

    expect(container).toHaveTextContent(/^Available$/)
  })
})

describe('Notice', () => {
  it('announces an error as an alert', () => {
    render(
      <Notice tone="error" title="We cannot search these dates">
        Choose a return date after the collection date.
      </Notice>,
    )

    const alert = screen.getByRole('alert')
    expect(within(alert).getByText('We cannot search these dates')).toBeVisible()
    expect(within(alert).getByText('Choose a return date after the collection date.')).toBeVisible()
  })

  it.each(['info', 'warn', 'success'] as const)(
    'announces a %s notice politely, as a status and not an alert',
    (tone) => {
      render(<Notice tone={tone} title="Your booking is held" />)

      expect(screen.getByRole('status')).toHaveTextContent('Your booking is held')
      expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    },
  )

  it('is a polite status when no tone is given', () => {
    render(<Notice title="Prices include VAT" />)

    expect(screen.getByRole('status')).toHaveTextContent('Prices include VAT')
  })
})

describe('Field', () => {
  it('ties the label to its control, so clicking the label focuses the input', async () => {
    const user = userEvent.setup()
    render(
      <Field label="Email address" htmlFor="email">
        <input id="email" type="email" />
      </Field>,
    )

    await user.click(screen.getByText('Email address'))

    expect(screen.getByLabelText('Email address')).toHaveFocus()
  })

  it('lets a person type into the labelled control', async () => {
    const user = userEvent.setup()
    render(
      <Field label="Email address" htmlFor="email">
        <input id="email" type="email" />
      </Field>,
    )

    await user.type(screen.getByLabelText('Email address'), 'thandi@example.com')

    expect(screen.getByLabelText('Email address')).toHaveValue('thandi@example.com')
  })

  it('shows the help text and the error text together', () => {
    render(
      <Field
        label="Email address"
        htmlFor="email"
        help="We send your booking confirmation here."
        error="Enter the email address on your account."
      >
        <input id="email" type="email" />
      </Field>,
    )

    expect(screen.getByText('We send your booking confirmation here.')).toBeVisible()
    expect(screen.getByText('Enter the email address on your account.')).toBeVisible()
  })
})

describe('PageHeader', () => {
  it('gives the screen one top level heading', () => {
    render(<PageHeader title="My reservations" subtitle="Everything you have booked." />)

    expect(screen.getByRole('heading', { level: 1, name: 'My reservations' })).toBeVisible()
    expect(screen.getByText('Everything you have booked.')).toBeVisible()
  })
})

describe('EmptyState', () => {
  it('says what is missing and offers the way forward', () => {
    render(
      <EmptyState
        title="Nothing matches that search"
        body="Try a wider date range."
        action={<button type="button">Clear the filters</button>}
      />,
    )

    expect(screen.getByText('Nothing matches that search')).toBeVisible()
    expect(screen.getByText('Try a wider date range.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Clear the filters' })).toBeVisible()
  })
})

describe('DataTable', () => {
  it('names the table by its caption and labels every column', () => {
    render(
      <DataTable caption="Overdue rentals" columns={['Customer', 'Due back', 'Days late']}>
        <tr>
          <td>Thandi Mokoena</td>
          <td>10 Mar 2026</td>
          <td>2</td>
        </tr>
      </DataTable>,
    )

    const table = screen.getByRole('table', { name: 'Overdue rentals' })
    const headers = within(table).getAllByRole('columnheader')
    expect(headers.map((header) => header.textContent)).toEqual(['Customer', 'Due back', 'Days late'])
    expect(within(table).getByRole('cell', { name: 'Thandi Mokoena' })).toBeVisible()
  })
})
