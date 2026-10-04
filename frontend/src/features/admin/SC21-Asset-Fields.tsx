/**
 * The paperwork of a unit on SC-21, the fields both forms share. The serial
 * number, the grade, the meter reading and the notes are typed when a unit is
 * registered and changed later in the same boxes.
 *
 * Every control is labelled and has its help and its error tied to it,
 * through the shared counter controls. Nothing here checks a value. The
 * server holds every rule, and its message for a field is passed in and shown
 * under that field.
 */

import type { ChangeEvent } from 'react'
import { CONDITION_GRADES } from '../../shared/api/rental-read'
import { Field } from '../../shared/ui'
import { SelectInput, TextArea, TextInput } from '../counter/counter-fields'
import { CONDITION_GRADE_LABEL } from '../counter/counter-labels'
import { assetFieldId } from './asset-form'
import type { AssetChangesDraft, AssetChangesField, NewAssetField } from './asset-form'

const GRADE_OPTIONS = CONDITION_GRADES.map((grade) => ({ value: grade, label: CONDITION_GRADE_LABEL[grade] }))

/** What a control needs from the form it sits in. */
export interface FieldControl {
  errorOf: (field: NewAssetField) => string | undefined
  disabled: boolean
}

/** A calendar day, `YYYY-MM-DD`, with its help and its error tied to it. */
export function DayInput({
  id,
  label,
  value,
  onChange,
  help,
  error,
  disabled,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  help?: string
  error?: string
  disabled?: boolean
}) {
  const describedBy = [help ? `${id}-help` : '', error ? `${id}-error` : ''].filter(Boolean).join(' ')
  return (
    <Field label={label} htmlFor={id} help={help} error={error}>
      <input
        id={id}
        name={id}
        type="date"
        value={value}
        disabled={disabled}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={`field-input cursor-pointer ${error ? 'border-status-overdue' : ''}`}
      />
    </Field>
  )
}

export function PaperworkFields({
  draft,
  onChange,
  control,
}: {
  draft: AssetChangesDraft
  onChange: (field: AssetChangesField, value: string) => void
  control: FieldControl
}) {
  function props(field: AssetChangesField) {
    return {
      id: assetFieldId(field),
      value: draft[field],
      onChange: (value: string) => onChange(field, value),
      error: control.errorOf(field),
      disabled: control.disabled,
    }
  }

  return (
    <>
      <TextInput
        {...props('serialNumber')}
        label="Serial number"
        help="The manufacturer's, from the plate on the unit. Leave it empty if it has none."
        autoComplete="off"
      />
      <SelectInput {...props('conditionGrade')} label="Condition grade" options={GRADE_OPTIONS} />
      <TextInput
        {...props('hourMeterReading')}
        label="Meter reading, in hours"
        help="Leave it empty if the unit has no hour meter."
        inputMode="numeric"
        autoComplete="off"
      />
      <div className="sm:col-span-2">
        <TextArea {...props('notes')} label="Notes" help="Anything the office should know about this unit. Optional." rows={3} />
      </div>
    </>
  )
}
