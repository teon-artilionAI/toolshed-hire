/**
 * One line of the hire basket on SC-04.
 *
 * It shows its working on the line itself, quantity times days times rate,
 * so the customer never has to trust the total at the bottom on faith. When
 * the branch cannot supply the quantity asked for, the line says so and
 * offers the fix as a button rather than telling the customer to work it
 * out themselves.
 */

import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import type { BranchCode, ProductModel, Uuid } from '../../shared/types'
import { money } from '../../shared/format'
import { Notice } from '../../shared/ui'
import type { BranchAvailability } from './availability'
import { fleetAt } from './availability'
import { QuantityStepper } from './catalogue-ui'

export default function BasketLine({
  model,
  quantity,
  days,
  hire,
  availability,
  short,
  branchCode,
  startIso,
  endIso,
  onChangeQuantity,
  onRemove,
}: {
  model: ProductModel
  quantity: number
  days: number
  /** Hire charge for this line, already worked out by the screen. */
  hire: number
  /** Null while the chosen period is unusable, so nothing is claimed. */
  availability: BranchAvailability | null
  short: boolean
  branchCode: BranchCode
  startIso: string
  endIso: string
  onChangeQuantity: (modelId: Uuid, quantity: number) => void
  onRemove: (modelId: Uuid) => void
}) {
  return (
    <li className="border-b border-line pb-lg last:border-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div className="min-w-0">
          <Link
            to={`/model/${model.id}?from=${startIso}&to=${endIso}&branch=${branchCode}`}
            className="inline-flex min-h-[2.75rem] cursor-pointer items-center text-base font-semibold text-ink underline decoration-line underline-offset-4 transition-colors duration-200 hover:decoration-accent"
          >
            {model.name}
          </Link>
          <p className="tabular mt-xs text-sm text-slate-soft">
            {money(model.dailyRate)} per day, {money(model.depositAmount)} deposit each
          </p>
        </div>
        <button type="button" className="btn-ghost px-md" onClick={() => onRemove(model.id)}>
          <Trash2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Remove
          <span className="sr-only"> {model.name} from the basket</span>
        </button>
      </div>

      <div className="mt-md flex flex-wrap items-end gap-lg">
        {/* Capped at the branch's whole fleet rather than at what is free, so
            asking for too many produces an explanation instead of a dead
            button. */}
        <QuantityStepper
          id={`qty-${model.id}`}
          itemLabel={model.name}
          value={quantity}
          max={Math.max(quantity, fleetAt(model.id, branchCode).length)}
          onChange={(next) => onChangeQuantity(model.id, next)}
        />
        <p className="tabular text-sm text-slate-soft">
          {quantity} × {days} {days === 1 ? 'day' : 'days'} × {money(model.dailyRate)} ={' '}
          <span className="font-semibold text-ink">{money(hire)}</span>
        </p>
      </div>

      {short && availability && (
        <div className="mt-md">
          <Notice
            tone="warn"
            title={
              availability.availableUnits === 0
                ? `None free at ${availability.branch.name}`
                : `Only ${availability.availableUnits} free at ${availability.branch.name}`
            }
          >
            <p>{availability.reason ?? 'The units here are already committed.'}</p>
            <button
              type="button"
              className="btn-secondary mt-sm px-md"
              onClick={() =>
                availability.availableUnits > 0
                  ? onChangeQuantity(model.id, availability.availableUnits)
                  : onRemove(model.id)
              }
            >
              {availability.availableUnits > 0
                ? `Take ${availability.availableUnits} instead`
                : 'Take it off the basket'}
            </button>
          </Notice>
        </div>
      )}
    </li>
  )
}
