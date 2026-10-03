/**
 * The units of a handover on SC-14, one block each.
 *
 * For each unit the assistant reads the tag off the unit and ticks it, records
 * the grade it goes out in, notes what goes with it, and reads the hour meter
 * when the unit has one. The grade starts at the one the unit has now and the
 * meter at its last reading, so most units need only the tick.
 *
 * Every control is tied to its own message, and every target is at least 44
 * pixels, because this is filled in standing at a counter.
 */

import { MAX_ACCESSORIES_LENGTH } from '../../shared/api/checkout'
import type { CheckoutUnit } from '../../shared/api/contract'
import { CONDITION_GRADES } from '../../shared/api/rental-read'
import { money } from '../../shared/format'
import { CheckRow, SelectInput, TextInput } from './counter-fields'
import { CONDITION_GRADE_LABEL } from './counter-labels'
import { unitControlId } from './checkout-form'
import type { CheckoutErrors, UnitDraft } from './checkout-form'

const GRADE_OPTIONS = CONDITION_GRADES.map((grade) => ({ value: grade, label: CONDITION_GRADE_LABEL[grade] }))

export function UnitFields({
  unit,
  index,
  answers,
  errors,
  disabled,
  onChange,
}: {
  unit: CheckoutUnit
  /** Where the unit sits on the reservation, counted from zero. */
  index: number
  answers: UnitDraft
  errors: CheckoutErrors
  disabled: boolean
  onChange: (patch: Partial<UnitDraft>) => void
}) {
  const id = (control: Parameters<typeof unitControlId>[1]) => unitControlId(index, control)
  return (
    <fieldset className="min-w-0 rounded-lg border border-line bg-surface p-md shadow-card" disabled={disabled}>
      <legend className="rounded bg-surface px-xs font-mono text-sm font-semibold text-ink">{unit.assetTag}</legend>
      <p className="mb-md text-sm text-slate-soft">
        {unit.modelName}. Its grade now is {CONDITION_GRADE_LABEL[unit.conditionGrade]}. Deposit{' '}
        {money(unit.depositPerUnit)}.
      </p>

      <CheckRow
        id={id('tag')}
        checked={answers.tagRead}
        onChange={(tagRead) => onChange({ tagRead })}
        error={errors[id('tag')]}
      >
        I have read the tag on the unit and it says <span className="font-mono">{unit.assetTag}</span>
      </CheckRow>

      <div className="mt-md grid gap-md sm:grid-cols-2">
        <SelectInput
          id={id('condition')}
          label="Condition going out"
          value={answers.conditionOut}
          onChange={(value) => {
            const grade = CONDITION_GRADES.find((known) => known === value)
            if (grade) onChange({ conditionOut: grade })
          }}
          options={GRADE_OPTIONS}
          error={errors[id('condition')]}
        />
        {unit.hourMeter === null ? (
          <p className="self-end rounded bg-muted p-sm text-sm text-slate-soft">
            This unit has no hour meter, so there is nothing to read.
          </p>
        ) : (
          <TextInput
            id={id('meter')}
            label="Hour meter reading"
            inputMode="numeric"
            help={`The last reading was ${unit.hourMeter} hours.`}
            value={answers.meter}
            onChange={(meter) => onChange({ meter })}
            error={errors[id('meter')]}
            autoComplete="off"
          />
        )}
      </div>
      <div className="mt-md">
        <TextInput
          id={id('accessories')}
          label="Accessories handed over"
          help="Optional. For example a chuck key and two bits. Leave it empty when nothing goes with it."
          value={answers.accessories}
          onChange={(accessories) => onChange({ accessories })}
          error={errors[id('accessories')]}
          maxLength={MAX_ACCESSORIES_LENGTH}
          autoComplete="off"
        />
      </div>
    </fieldset>
  )
}
