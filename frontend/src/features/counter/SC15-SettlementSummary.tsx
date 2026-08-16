/**
 * The deposit settlement panel for SC-15.
 *
 * It is a real table because it is a column of figures that has to add up in
 * front of a customer. Deductions are shown as negatives on their own lines
 * so the arithmetic reads the way it would on a paper slip, and the deposit
 * cannot be released while a unit is still out.
 */

import { Notice, Card, DataTable } from '../../shared/ui'
import { money } from '../../shared/format'

function AmountRow({
  label,
  amount,
  negative = false,
  strong = false,
}: {
  label: string
  amount: number
  negative?: boolean
  strong?: boolean
}) {
  return (
    <tr className={strong ? 'bg-muted' : undefined}>
      <th
        scope="row"
        className={`td text-left font-normal ${strong ? 'font-semibold text-ink' : 'text-slate-soft'}`}
      >
        {label}
      </th>
      <td
        className={`td tabular whitespace-nowrap text-right font-mono ${
          strong ? 'text-base font-semibold text-ink' : 'text-ink'
        }`}
      >
        {negative ? `- ${money(amount)}` : money(amount)}
      </td>
    </tr>
  )
}

export function SettlementSummary({
  deposit,
  lateFee,
  damage,
  blockedBy,
  settled,
  onSettle,
  customerName,
  reference,
}: {
  deposit: number
  lateFee: number
  damage: number
  /** Tags of units not yet back. While this has anything in it, nothing is
   *  released, and the screen says which unit is holding it up. */
  blockedBy: string[]
  settled: boolean
  onSettle: () => void
  customerName: string
  reference: string
}) {
  const withheld = lateFee + damage
  const released = Math.max(0, deposit - withheld)
  const owing = Math.max(0, withheld - deposit)

  return (
    <Card title="Deposit settlement">
      <DataTable
        columns={['Line', 'Amount']}
        caption={`How the ${money(deposit)} deposit on ${reference} is settled`}
      >
        <AmountRow label="Deposit held at collection" amount={deposit} />
        <AmountRow label="Less late fees" amount={lateFee} negative />
        <AmountRow label="Less damage charged" amount={damage} negative />
        <AmountRow label="Released to the customer" amount={released} strong />
      </DataTable>

      <p className="tabular mt-md font-mono text-sm text-slate-soft">
        {money(deposit)} - {money(lateFee)} - {money(damage)} = {money(released)}
      </p>

      {owing > 0 && (
        <div className="mt-md">
          <Notice tone="error" title="The deposit does not cover the charges">
            The late fee and damage come to {money(withheld)}, which is more than
            the {money(deposit)} deposit. {customerName} still owes{' '}
            {money(owing)}. Take that at the counter before the hire is closed.
          </Notice>
        </div>
      )}

      <div className="mt-lg border-t border-line pt-md">
        {settled ? (
          <Notice tone="success" title={`${reference} is settled`}>
            {money(released)} released to {customerName}. The units are back on
            the shelf and the hire is closed.
          </Notice>
        ) : blockedBy.length > 0 ? (
          <>
            <Notice tone="warn" title="Nothing can be released yet">
              {blockedBy.join(', ')}{' '}
              {blockedBy.length === 1 ? 'is' : 'are'} still out. Tick each unit
              off as it comes back onto the counter, then settle the deposit.
            </Notice>
            <button type="button" className="btn-secondary mt-md px-md" disabled>
              Release {money(released)}
            </button>
          </>
        ) : (
          <>
            <p className="mb-md text-sm text-slate-soft">
              Everything is back. Releasing settles the hire and returns the
              units to stock.
            </p>
            <button type="button" className="btn-primary px-md" onClick={onSettle}>
              Release {money(released)} and close the hire
            </button>
          </>
        )}
      </div>
    </Card>
  )
}
