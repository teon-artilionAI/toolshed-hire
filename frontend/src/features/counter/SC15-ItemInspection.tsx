/**
 * One unit on SC-15. A unit still out, being inspected on its way back in, a
 * unit that is already back, or a unit recorded as lost from the overdue
 * worklist.
 *
 * A unit still out says what the late fee is if it comes back today. That is
 * the server's figure, `lateFeeToday` for `daysLateToday` days, and the screen
 * says the system worked it out, that the counter confirms it and cannot change
 * it, and that only the owner can waive a charge. The browser works out no fee.
 *
 * Ticking the unit opens what is recorded about it. The grade coming back sits
 * next to the grade it went out at, because the only question that matters at
 * a return counter is whether those two differ, and the screen says so in
 * words when they do.
 */

import { CheckCircle2, TriangleAlert } from 'lucide-react'
import { MAX_ACCESSORIES_LENGTH } from '../../shared/api/checkout'
import type { RentalCharge, RentalItem } from '../../shared/api/contract'
import { CONDITION_GRADES } from '../../shared/api/rental-read'
import { isNegativeMoney, money, unsignedMoney } from '../../shared/format'
import { branchDateTime } from '../../shared/today'
import { Notice, StatusPill } from '../../shared/ui'
import { CheckRow, SelectInput, TextInput } from './counter-fields'
import { CHARGE_TYPE_LABEL, CONDITION_GRADE_LABEL, countOf } from './counter-labels'
import { isLost, isWorse, itemControlId, itemLabel } from './SC15-return-model'
import type { ItemDraft, ReturnErrors } from './SC15-return-model'

const GRADE_OPTIONS = CONDITION_GRADES.map((grade) => ({ value: grade, label: CONDITION_GRADE_LABEL[grade] }))

/** Said beside every late fee on the screen (US-25, US-29). */
export const LATE_FEE_IS_THE_SYSTEMS =
  'The system worked this fee out from the late fee policy. The counter confirms it with the return and cannot change it.'

/** Said where a fee may look wrong. */
export const ONLY_THE_OWNER_WAIVES =
  'If it looks wrong, take the unit back anyway and tell the owner. Only the owner can waive a charge.'

/** How the unit went out, in one line. */
function wentOut(item: RentalItem): string {
  const meter = item.hourMeterOut === null ? '' : `, ${item.hourMeterOut} hours on the meter`
  const accessories = item.accessoriesOut ? `, with ${item.accessoriesOut}` : ''
  return `${item.modelName}. Went out at ${CONDITION_GRADE_LABEL[item.conditionOut]}${meter}${accessories}.`
}

/** The late fee the server gives if the unit comes back today. */
function LateFeeToday({ item }: { item: RentalItem }) {
  if (item.daysLateToday === 0) {
    return (
      <p className="rounded bg-muted p-sm text-sm text-slate-soft">
        Not late. If it comes back today there is no late fee.
      </p>
    )
  }
  return (
    <div className="rounded border-l-4 border-status-due bg-status-due-wash p-sm text-sm text-ink">
      <p className="tabular font-semibold">
        {countOf(item.daysLateToday, 'day', 'days')} late. Late fee if it comes back today {money(item.lateFeeToday)}.
      </p>
      <p className="tabular mt-xs">The daily late fee for this model is {money(item.lateFeePerDay)}.</p>
      <p className="mt-xs">{LATE_FEE_IS_THE_SYSTEMS}</p>
      <p className="mt-xs">{ONLY_THE_OWNER_WAIVES}</p>
    </div>
  )
}

export function ItemInspection({
  item,
  answers,
  errors,
  disabled,
  onChange,
}: {
  item: RentalItem
  answers: ItemDraft
  errors: ReturnErrors
  disabled: boolean
  onChange: (patch: Partial<ItemDraft>) => void
}) {
  const id = (control: Parameters<typeof itemControlId>[1]) => itemControlId(item.id, control)
  const worse = isWorse(answers.conditionIn, item.conditionOut)
  return (
    <fieldset className="min-w-0 rounded-lg border border-line bg-surface p-md shadow-card" disabled={disabled}>
      <legend className="rounded bg-surface px-xs font-mono text-sm font-semibold text-ink">{itemLabel(item)}</legend>
      <p className="mb-md break-words text-sm text-slate-soft">{wentOut(item)}</p>
      <div className="mb-md">
        <LateFeeToday item={item} />
      </div>

      <CheckRow
        id={id('returning')}
        checked={answers.returning}
        onChange={(returning) => onChange({ returning })}
        error={errors[id('returning')]}
      >
        <span className="font-mono">{itemLabel(item)}</span> is back on the counter. Take it back now.
      </CheckRow>

      {answers.returning && (
        <div className="mt-md flex flex-col gap-md">
          <div className="grid gap-md sm:grid-cols-2">
            <SelectInput
              id={id('condition')}
              label="Condition coming back"
              help={`It went out at ${CONDITION_GRADE_LABEL[item.conditionOut]}.`}
              value={answers.conditionIn}
              onChange={(value) => {
                const grade = CONDITION_GRADES.find((known) => known === value)
                if (grade) onChange({ conditionIn: grade })
              }}
              options={GRADE_OPTIONS}
              error={errors[id('condition')]}
            />
            {item.hourMeterOut === null ? (
              <p className="self-end rounded bg-muted p-sm text-sm text-slate-soft">
                This unit has no hour meter, so there is nothing to read.
              </p>
            ) : (
              <TextInput
                id={id('meter')}
                label="Hour meter reading"
                inputMode="numeric"
                help={`It read ${item.hourMeterOut} hours going out.`}
                value={answers.meter}
                onChange={(meter) => onChange({ meter })}
                error={errors[id('meter')]}
                autoComplete="off"
              />
            )}
          </div>
          <TextInput
            id={id('accessories')}
            label="Accessories that came back"
            help="Optional. Leave it empty when nothing came back with it."
            value={answers.accessories}
            onChange={(accessories) => onChange({ accessories })}
            error={errors[id('accessories')]}
            maxLength={MAX_ACCESSORIES_LENGTH}
            autoComplete="off"
          />
          <CheckRow
            id={id('damage')}
            checked={answers.flaggedForDamage}
            onChange={(flaggedForDamage) => onChange({ flaggedForDamage })}
            error={errors[id('damage')]}
          >
            Flag for damage. Tick this when something is wrong with it, even if the grade has not changed.
          </CheckRow>
          {worse ? (
            <Notice tone="warn" title="This unit is coming back worse than it went out">
              <p>
                Out at {CONDITION_GRADE_LABEL[item.conditionOut]}, back at {CONDITION_GRADE_LABEL[answers.conditionIn]}.
                The server keeps both grades with the return.
              </p>
            </Notice>
          ) : (
            <p className="flex items-center gap-xs text-sm text-status-available">
              <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              Coming back at the grade it went out at.
            </p>
          )}
        </div>
      )}
    </fieldset>
  )
}

/**
 * A unit recorded as lost, with when and what the loss charged. The charges
 * are the server's, the ones that carry this unit's id, other than its hire.
 */
function LostItem({ item, charges }: { item: RentalItem; charges: readonly RentalCharge[] }) {
  const forTheLoss = charges.filter((charge) => charge.rentalItemId === item.id && charge.type !== 'HIRE')
  return (
    <div className="min-w-0 rounded-lg border border-line bg-muted p-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <p className="font-mono text-sm font-semibold text-ink">{itemLabel(item)}</p>
        <StatusPill status="LOST" label="Recorded as lost" />
      </div>
      <p className="mt-xs break-words text-sm text-ink">
        {item.modelName}. Recorded as lost {item.returnedAt === null ? '' : branchDateTime(item.returnedAt)},{' '}
        {countOf(item.daysLate, 'day', 'days')} after it was due back.
      </p>
      {forTheLoss.length > 0 && (
        <ul aria-label={`Charges for the loss of ${itemLabel(item)}`} className="mt-xs flex flex-col gap-xs text-sm">
          {forTheLoss.map((charge) => (
            <li key={charge.id} className="tabular break-words text-slate-soft">
              {CHARGE_TYPE_LABEL[charge.type]}. {charge.description}{' '}
              {isNegativeMoney(charge.amountIncVat)
                ? `${unsignedMoney(charge.amountIncVat)} back to the customer`
                : money(charge.amountIncVat)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** A unit that is already back, with when, how and what it was charged. A unit
 *  recorded as lost is closed too, and says so instead. */
export function ReturnedItem({ item, charges }: { item: RentalItem; charges: readonly RentalCharge[] }) {
  if (isLost(item)) return <LostItem item={item} charges={charges} />
  const lateFees = charges.filter((charge) => charge.type === 'LATE_FEE' && charge.rentalItemId === item.id)
  return (
    <div className="min-w-0 rounded-lg border border-line bg-muted p-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <p className="font-mono text-sm font-semibold text-ink">{itemLabel(item)}</p>
        <StatusPill status="RETURNED" label="Back" />
      </div>
      <p className="mt-xs break-words text-sm text-ink">
        {item.modelName}. Back {item.returnedAt === null ? '' : branchDateTime(item.returnedAt)} at{' '}
        {item.conditionIn === null ? 'no grade on record' : CONDITION_GRADE_LABEL[item.conditionIn]}
        {item.hourMeterIn === null ? '' : `, ${item.hourMeterIn} hours on the meter`}
        {item.accessoriesIn ? `, with ${item.accessoriesIn}` : ''}.
      </p>
      <p className="tabular mt-xs text-sm text-slate-soft">
        {item.daysLate === 0 ? 'Back on time.' : `Back ${countOf(item.daysLate, 'day', 'days')} late.`}
        {lateFees.map((charge) => ` Late fee charged ${money(charge.amountIncVat)}.`).join('')}
      </p>
      {item.damageAssessment === 'REQUIRED' && (
        <p className="mt-xs flex items-center gap-xs text-sm text-status-overdue">
          <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
          Waiting for a damage report.
        </p>
      )}
      {item.damageAssessment === 'DONE' && <p className="mt-xs text-sm text-slate-soft">The damage report is filed.</p>}
    </div>
  )
}
