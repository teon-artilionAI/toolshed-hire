/**
 * The question that sets a trade customer's discount on SC-23.
 *
 * It starts with the value the server sent, so a change is typed against what
 * the customer actually carries. The confirmation says which customer it is,
 * that the discount applies from the next booking, and that existing bookings
 * keep the discount they were made with. A refusal from the server appears
 * under the input, and the question stays open so it can be corrected.
 */

import { useState } from 'react'
import type { CustomerSummary, TradeDiscountRequest } from '../../shared/api/contract'
import { setTradeDiscount } from '../../shared/api/admin-customers'
import { fieldErrorsFromProblem, isRefusal, otherFieldMessages } from '../../shared/api/problem-fields'
import { TextInput } from '../counter/counter-fields'
import { ErrorState } from '../../shared/async-states'

const FIELD = 'tradeDiscountPercent'
const FIELD_LABELS: readonly string[] = [FIELD]

export function TradeDiscountQuestion({
  customer,
  onChanged,
  onCancel,
}: {
  customer: CustomerSummary
  onChanged: (customer: CustomerSummary) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState(customer.tradeDiscountPercent)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<unknown>(null)
  const [fieldError, setFieldError] = useState<string | undefined>(undefined)
  const [otherMessages, setOtherMessages] = useState<string[]>([])

  async function save() {
    if (busy) return
    setBusy(true)
    setFailure(null)
    setFieldError(undefined)
    setOtherMessages([])
    const body: TradeDiscountRequest = { tradeDiscountPercent: value.trim() }
    try {
      onChanged(await setTradeDiscount(customer.id, body))
    } catch (error) {
      const fields = fieldErrorsFromProblem(error)
      setFieldError(fields[FIELD])
      setOtherMessages(otherFieldMessages(fields, FIELD_LABELS))
      if (!isRefusal(error)) setFailure(error)
      setBusy(false)
    }
  }

  return (
    <section aria-label={`Set the trade discount for ${customer.displayName}`} className="rounded-md border border-line p-md">
      <h4 className="text-sm font-semibold text-ink">Set a trade discount</h4>
      <p className="mt-xs text-sm text-slate-soft">
        {customer.displayName} carries {customer.tradeDiscountPercent}% now. A new value applies
        to bookings made from now on. Existing bookings keep the discount they were made with.
      </p>
      <div className="mt-sm flex flex-wrap items-end gap-sm">
        <TextInput
          id={`trade-discount-${customer.id}`}
          label="Trade discount percent"
          type="text"
          inputMode="decimal"
          value={value}
          onChange={setValue}
          error={fieldError}
        />
        <button type="button" className="btn-primary px-md" onClick={() => void save()} disabled={busy}>
          {busy ? 'Saving' : 'Set the discount'}
        </button>
        <button type="button" className="btn-secondary px-md" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
      {otherMessages.length > 0 && (
        <ul className="mt-sm list-disc pl-lg text-sm text-ink">
          {otherMessages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      {failure !== null && (
        <div className="mt-sm">
          <ErrorState
            heading="We could not set the discount"
            error={failure}
            onRetry={() => void save()}
          />
        </div>
      )}
    </section>
  )
}
