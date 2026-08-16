/**
 * What happened after a booking was collected.
 *
 * Once equipment leaves the branch the booking stops being the interesting
 * object and the hire takes over: what is still out, when it is due, and
 * what is coming off the deposit. Shown on SC-08 under the booking it grew
 * out of, so the customer never has to hold two references in their head.
 */

import { assets, charges, productModels } from '../../shared/fixtures'
import {
  daysOverdue,
  formatDate,
  formatDateTime,
  isOverdue,
  money,
} from '../../shared/format'
import type { Rental } from '../../shared/types'
import { Card, Notice, StatusPill } from '../../shared/ui'
import { CHARGE_KIND_LABEL, RENTAL_STATUS_LABEL } from './customer-labels'

function assetLabel(assetId: string): { tag: string; model: string } {
  const asset = assets.find((candidate) => candidate.id === assetId)
  if (!asset) return { tag: 'Unknown unit', model: '' }
  const model = productModels.find((m) => m.id === asset.productModelId)
  return {
    tag: asset.tag,
    model: model ? `${model.manufacturer} ${model.name}` : '',
  }
}

export function HireProgressCard({ rental }: { rental: Rental }) {
  const late = isOverdue(rental.dueBackOn)
  const lateDays = daysOverdue(rental.dueBackOn)
  const rentalCharges = charges.filter((charge) => charge.rentalId === rental.id)
  const toDeduct = rentalCharges
    .filter((charge) => !charge.settled && charge.kind !== 'DEPOSIT')
    .reduce((sum, charge) => sum + charge.amount, 0)
  const stillOut = rental.items.filter((item) => !item.returnedAt)

  return (
    <Card title="This hire is under way">
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div>
          <p className="font-mono text-sm font-medium text-ink">
            {rental.reference}
          </p>
          <p className="mt-xs text-sm text-slate-soft">
            Collected {formatDateTime(rental.collectedAt)}
          </p>
        </div>
        <StatusPill
          status={rental.status}
          label={RENTAL_STATUS_LABEL[rental.status]}
        />
      </div>

      {late && stillOut.length > 0 && (
        <div className="mt-md">
          <Notice
            tone="error"
            title={`${lateDays} ${lateDays === 1 ? 'day' : 'days'} past the return date`}
          >
            <p>
              This was due back on {formatDate(rental.dueBackOn)}. A late fee is
              added for every day it stays out and comes off the deposit when
              the equipment is returned.
            </p>
          </Notice>
        </div>
      )}

      <ul className="mt-md flex flex-col gap-sm">
        {rental.items.map((item) => {
          const { tag, model } = assetLabel(item.assetId)
          return (
            <li
              key={item.id}
              className="flex flex-wrap items-baseline justify-between gap-sm
                         border-b border-line pb-sm last:border-0 last:pb-0"
            >
              <span>
                <span className="font-mono text-sm text-ink">{tag}</span>
                <span className="ml-sm text-sm text-slate-soft">{model}</span>
              </span>
              {item.returnedAt ? (
                <span className="text-sm text-status-available">
                  Returned {formatDate(item.returnedAt)}
                </span>
              ) : (
                <span
                  className={`text-sm ${late ? 'font-medium text-status-overdue' : 'text-slate-soft'}`}
                >
                  {late ? 'Still with you, past due' : 'Still with you'}
                </span>
              )}
            </li>
          )
        })}
      </ul>

      <dl className="mt-lg grid gap-sm border-t border-line pt-md text-sm sm:grid-cols-2">
        <div className="flex justify-between gap-md sm:col-span-2">
          <dt className="text-slate-soft">Deposit held</dt>
          <dd className="tabular font-medium text-ink">
            {money(rental.depositHeld)}
          </dd>
        </div>
        {rentalCharges
          .filter((charge) => !charge.settled && charge.kind !== 'DEPOSIT')
          .map((charge) => (
            <div
              key={charge.id}
              className="flex justify-between gap-md sm:col-span-2"
            >
              <dt className="text-slate-soft">
                {CHARGE_KIND_LABEL[charge.kind]}, {charge.description}
              </dt>
              <dd className="tabular font-medium text-status-overdue">
                minus {money(charge.amount)}
              </dd>
            </div>
          ))}
        <div className="flex justify-between gap-md border-t border-line pt-sm sm:col-span-2">
          <dt className="font-medium text-ink">
            Expected back when everything is returned
          </dt>
          <dd className="tabular font-semibold text-ink">
            {money(Math.max(0, rental.depositHeld - toDeduct))}
          </dd>
        </div>
      </dl>
    </Card>
  )
}
