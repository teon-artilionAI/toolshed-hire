/**
 * Customer account holds, the second half of SC-23.
 *
 * A hold stops a customer booking anything new without deleting their
 * history, which is what the counter actually needs after a second no show.
 * Riaan van Wyk is on hold in the fixture data, so the state is visible from
 * the moment the screen loads.
 *
 * Placing a hold asks for a reason before it will go through. Somebody has
 * to explain this to the customer later, and "no reason given" is not an
 * explanation.
 */

import { useState } from 'react'
import { Lock, Unlock } from 'lucide-react'
import { formatDate } from '../../shared/format'
import type { CustomerProfile } from '../../shared/types'
import { DataTable, EmptyState, Field, StatusPill } from '../../shared/ui'

export interface HoldChange {
  customerId: string
  onHold: boolean
  reason: string
}

export default function CustomerHolds({
  customers,
  query,
  onChange,
}: {
  customers: CustomerProfile[]
  query: string
  onChange: (change: HoldChange) => void
}) {
  const [holdingId, setHoldingId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | undefined>()

  const needle = query.trim().toLowerCase()
  const shown = needle
    ? customers.filter(
        (c) =>
          c.name.toLowerCase().includes(needle) ||
          c.email.toLowerCase().includes(needle),
      )
    : customers

  function startHold(customerId: string) {
    setHoldingId(customerId)
    setReason('')
    setReasonError(undefined)
  }

  function confirmHold(customerId: string) {
    if (reason.trim().length < 4) {
      setReasonError(
        'Say why in a few words. It is shown to whoever picks this up at the counter.',
      )
      return
    }
    onChange({ customerId, onHold: true, reason: reason.trim() })
    setHoldingId(null)
    setReason('')
    setReasonError(undefined)
  }

  if (shown.length === 0) {
    return (
      <EmptyState
        title="No customer matches that search"
        body="Try part of a surname or an email address. The search looks at both."
      />
    )
  }

  return (
    <DataTable
      columns={['Customer', 'Where they are', 'With us since', 'Standing', 'Action']}
      caption="Customer accounts and their hold status"
    >
      {shown.map((customer) => (
        <tr
          key={customer.id}
          className="transition-colors duration-200 hover:bg-muted"
        >
          <th scope="row" className="td text-left font-medium text-ink">
            {customer.name}
            <span className="mt-xs block text-xs font-normal text-slate-soft">
              {customer.email}
            </span>
          </th>
          <td className="td text-slate-soft">
            {customer.billingSuburb}, {customer.billingCity}
          </td>
          <td className="td tabular text-slate-soft">
            {formatDate(customer.joinedOn)}
          </td>
          <td className="td">
            {customer.onHold ? (
              <StatusPill status="OVERDUE" label="On hold" />
            ) : (
              <StatusPill status="AVAILABLE" label="In good standing" />
            )}
          </td>
          <td className="td">
            {customer.onHold ? (
              <button
                type="button"
                className="btn-secondary px-md"
                onClick={() =>
                  onChange({
                    customerId: customer.id,
                    onHold: false,
                    reason: 'Hold lifted',
                  })
                }
              >
                <Unlock className="h-4 w-4 shrink-0" aria-hidden="true" />
                Lift the hold
              </button>
            ) : holdingId === customer.id ? (
              <div className="flex flex-col gap-sm">
                <Field
                  label={`Why is ${customer.name} going on hold?`}
                  htmlFor={`hold-reason-${customer.id}`}
                  error={reasonError}
                >
                  <input
                    id={`hold-reason-${customer.id}`}
                    className="field-input"
                    value={reason}
                    autoFocus
                    aria-invalid={reasonError ? true : undefined}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </Field>
                <div className="flex flex-wrap gap-sm">
                  <button
                    type="button"
                    className="btn-danger px-md"
                    onClick={() => confirmHold(customer.id)}
                  >
                    Place on hold
                  </button>
                  <button
                    type="button"
                    className="btn-secondary px-md"
                    onClick={() => setHoldingId(null)}
                  >
                    Leave it
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="btn-secondary px-md"
                onClick={() => startHold(customer.id)}
              >
                <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
                Place on hold
              </button>
            )}
          </td>
        </tr>
      ))}
    </DataTable>
  )
}
