/**
 * The deposit settlement on SC-15, once every unit is back.
 *
 * Every figure is the server's. The deposit held, what was withheld, what was
 * released and the balance due are read off the hire. Under them are the
 * charges the server set against the deposit, with the sentence it wrote for
 * each and whether it is settled yet. Nothing here adds anything up.
 *
 * The figures are a real table, because they are a column of money read out to
 * a customer. A deposit given back is written as released, never with a bare
 * minus sign.
 *
 * When the server says the deposit is still waiting, the panel says on what.
 * A balance the deposit did not cover is taken at the counter, through the
 * form in SC15-Balance-Payment.tsx. A unit waiting for a damage report links
 * to the damage screen for that unit.
 */

import { Link } from 'react-router-dom'
import { TriangleAlert } from 'lucide-react'
import type { ChargeType, Rental, RentalCharge } from '../../shared/api/contract'
import { isNegativeMoney, isNoMoney, money, unsignedMoney } from '../../shared/format'
import { branchDateTime } from '../../shared/today'
import { Card, DataTable, Notice } from '../../shared/ui'
import { CHARGE_STATUS_LABEL, CHARGE_TYPE_LABEL } from './counter-labels'
import { damageHref } from './counter-links'
import { BalancePayment } from './SC15-Balance-Payment'
import { itemLabel } from './SC15-return-model'

/** The charges that come off a deposit. A hire charge and the deposit itself
 *  are not reasons to withhold anything. */
const WITHHOLDING_CHARGES: readonly ChargeType[] = [
  'LATE_FEE',
  'DAMAGE_RECOVERY',
  'DEPOSIT_FORFEIT',
  'CLEANING',
  'ADJUSTMENT',
]

/** An amount in words that say which way it runs. */
function amountInWords(amount: string): string {
  return isNegativeMoney(amount) ? `${unsignedMoney(amount)} back to the customer` : money(amount)
}

function FigureRow({ label, amount, strong = false }: { label: string; amount: string; strong?: boolean }) {
  return (
    <tr className={strong ? 'bg-muted' : undefined}>
      <th scope="row" className={`td text-left ${strong ? 'font-semibold text-ink' : 'font-normal text-slate-soft'}`}>
        {label}
      </th>
      <td className={`td tabular whitespace-nowrap text-right font-mono ${strong ? 'font-semibold' : ''} text-ink`}>
        {amount}
      </td>
    </tr>
  )
}

/**
 * The charges set against the deposit, each with where it stands. When the
 * deposit covers them all they are settled with it. When it does not, the
 * server keeps a charge it covered only in part pending until the balance is
 * paid, so the list can come to more than was withheld.
 */
function ChargedAgainstDeposit({ charges }: { charges: readonly RentalCharge[] }) {
  if (charges.length === 0) return <p className="mt-md text-sm text-slate-soft">Nothing was charged against the deposit.</p>
  return (
    <div className="mt-md">
      <h3 className="text-sm font-semibold text-ink">Charged against the deposit</h3>
      <ul className="mt-xs flex flex-col gap-xs">
        {charges.map((charge) => (
          <li key={charge.id} className="flex flex-wrap justify-between gap-x-md gap-y-xs rounded bg-muted p-sm text-sm">
            <span className="min-w-0 break-words text-ink">
              {CHARGE_TYPE_LABEL[charge.type]}. {charge.description}
              <span className="block text-xs text-slate-soft">{CHARGE_STATUS_LABEL[charge.status]}</span>
            </span>
            <span className="tabular font-mono text-ink">{amountInWords(charge.amountIncVat)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** What the deposit is still waiting on, when anything. */
function Waiting({ rental, onPaid }: { rental: Rental; onPaid: (rental: Rental) => void }) {
  if (rental.settlementWaitingOn === 'BALANCE_PAYMENT') {
    return (
      <div className="mt-lg flex flex-col gap-md border-t border-line pt-md">
        <Notice tone="warn" title="The deposit does not cover the charges">
          <p>
            {rental.customerName} owes a balance of {money(rental.balanceDue)}. Take it at the counter and record the
            reference of the payment, and the hire is settled.
          </p>
        </Notice>
        <BalancePayment rental={rental} onPaid={onPaid} />
      </div>
    )
  }
  if (rental.settlementWaitingOn === 'DAMAGE_ASSESSMENT') {
    const waiting = rental.items.filter((item) => item.damageAssessment === 'REQUIRED')
    return (
      <div className="mt-lg border-t border-line pt-md">
        <Notice tone="warn" title="The deposit is waiting for a damage report">
          <p>It is settled once every unit that came back damaged has its report.</p>
        </Notice>
        <ul className="mt-md flex flex-col gap-sm">
          {waiting.map((item) => (
            <li key={item.id}>
              {item.assetTag === null ? (
                <p className="text-sm text-ink">{item.modelName} has no tag on record, so report it from the asset register.</p>
              ) : (
                <Link
                  to={damageHref(item.assetTag, { rentalId: rental.id, rentalItemId: item.id })}
                  className="btn-secondary px-md"
                >
                  <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
                  Record the damage to {itemLabel(item)}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return null
}

/** Said once the server has settled the deposit. */
function Settled({ rental }: { rental: Rental }) {
  if (rental.settledAt === null) return null
  const inFull = isNoMoney(rental.depositWithheld)
  return (
    <div className="mb-md">
      <Notice tone="success" title={`${rental.reference} is settled`}>
        <p>
          Settled {branchDateTime(rental.settledAt)}.{' '}
          {inFull
            ? `The deposit of ${money(rental.depositHeld)} was released in full.`
            : `${money(rental.depositRefunded)} of the ${money(rental.depositHeld)} deposit was released.`}{' '}
          {isNoMoney(rental.balanceDue) ? 'Nothing is due.' : `The balance due is ${money(rental.balanceDue)}.`}
        </p>
      </Notice>
    </div>
  )
}

export function SettlementSummary({ rental, onPaid }: { rental: Rental; onPaid: (rental: Rental) => void }) {
  const charged = rental.charges.filter((charge) => WITHHOLDING_CHARGES.includes(charge.type))
  return (
    <Card title="Deposit settlement">
      <Settled rental={rental} />
      <DataTable columns={['Line', 'Amount']} caption={`How the deposit on ${rental.reference} is settled`}>
        <FigureRow label="Deposit held at collection" amount={money(rental.depositHeld)} />
        <FigureRow label="Withheld from the deposit" amount={money(rental.depositWithheld)} />
        <FigureRow label="Released to the customer" amount={money(rental.depositRefunded)} strong />
        <FigureRow label="Balance due" amount={money(rental.balanceDue)} strong />
      </DataTable>
      <ChargedAgainstDeposit charges={charged} />
      <Waiting rental={rental} onPaid={onPaid} />
    </Card>
  )
}
