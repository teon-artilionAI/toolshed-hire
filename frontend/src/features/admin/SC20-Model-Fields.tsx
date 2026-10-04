/**
 * The fields of the model form on SC-20, in four groups.
 *
 * What the model is, how customers read about it, what it costs, and how long
 * it may be hired for. Each group is a fieldset with a legend, and every
 * control is labelled and has its help and its error tied to it, through the
 * shared counter controls.
 *
 * The stock code is typed only while a model is being added. Once the model
 * exists it is shown read only, because it never changes.
 *
 * Nothing here checks a value. The server holds every rule, and its message
 * for a field is passed in and shown under that field.
 */

import type { ReactNode } from 'react'
import type { AdminCategory } from '../../shared/api/contract'
import { SelectInput, TextArea, TextInput } from '../counter/counter-fields'
import { categoryOptionLabel } from './catalogue-labels'
import { MONEY_FIELDS, MONEY_LABEL, modelFieldId } from './model-form'
import type { ModelDraft, ModelField, MoneyField } from './model-form'

/** What each figure is for, under its box. */
const MONEY_HELP: Record<MoneyField, string> = {
  dailyRate: 'For one unit for one day, excluding VAT.',
  weeklyRate: 'For one unit for each whole week, excluding VAT.',
  depositAmount: 'Held for each unit at collection and released at return.',
  lateFeePerDay: 'Charged for each day a unit comes back late.',
  replacementValue: 'What another unit would cost. A damage charge for one unit never comes to more.',
}

const NO_CATEGORY = ''

function Group({
  legend,
  help,
  wide = false,
  children,
}: {
  legend: string
  help?: string
  /** One control to a line at every width, for boxes of several lines. */
  wide?: boolean
  children: ReactNode
}) {
  return (
    <fieldset className="min-w-0">
      <legend className="mb-sm text-base font-semibold text-ink">{legend}</legend>
      {help && <p className="mb-sm text-sm text-slate-soft">{help}</p>}
      <div className={`grid gap-md ${wide ? '' : 'sm:grid-cols-2'}`}>{children}</div>
    </fieldset>
  )
}

export function ModelFields({
  draft,
  sku,
  categories,
  errorOf,
  onChange,
  disabled,
}: {
  draft: ModelDraft
  /** The stock code of a model that exists, shown read only. Null while one is
   *  being added, when it is typed. */
  sku: string | null
  categories: readonly AdminCategory[]
  errorOf: (field: ModelField) => string | undefined
  onChange: (field: ModelField, value: string) => void
  disabled: boolean
}) {
  function control(field: ModelField) {
    return {
      id: modelFieldId(field),
      value: draft[field],
      onChange: (value: string) => onChange(field, value),
      error: errorOf(field),
      disabled,
    }
  }

  const categoryOptions = [
    ...(sku === null ? [{ value: NO_CATEGORY, label: 'Choose a category' }] : []),
    ...categories.map((category) => ({ value: category.id, label: categoryOptionLabel(category) })),
  ]

  return (
    <div className="flex flex-col gap-lg">
      <Group legend="What it is">
        {sku === null ? (
          <TextInput
            {...control('sku')}
            label="Stock code"
            help="As printed on the shelf label. It cannot be changed once the model is added."
            autoComplete="off"
          />
        ) : (
          <div>
            <p className="field-label">Stock code</p>
            <p className="break-all py-sm font-mono text-base text-ink">{sku}</p>
            <p className="field-help">A stock code never changes once the model is in the catalogue.</p>
          </div>
        )}
        <TextInput {...control('name')} label="Name" help="As a customer would search for it." autoComplete="off" />
        <TextInput
          {...control('slug')}
          label="Name in the web address"
          help="For example cp-100-plate-compactor."
          autoComplete="off"
        />
        <SelectInput {...control('categoryId')} label="Category it sits in" options={categoryOptions} />
        <TextInput {...control('manufacturer')} label="Manufacturer" autoComplete="off" />
        <TextInput {...control('modelNumber')} label="Model number" help="The manufacturer's own." autoComplete="off" />
      </Group>

      <Group legend="What customers read" wide>
        <TextArea {...control('shortDescription')} label="Short description" help="One or two sentences for the list." rows={2} />
        <TextArea {...control('longDescription')} label="Full description" help="Optional." rows={4} />
      </Group>

      <Group
        legend="What it costs"
        help="Amounts in rand. Bookings already made keep the figures they were booked at, so a change here reaches new bookings only."
      >
        {MONEY_FIELDS.map((field) => (
          <TextInput
            key={field}
            {...control(field)}
            label={`${MONEY_LABEL[field]}, in rand`}
            help={MONEY_HELP[field]}
            inputMode="decimal"
            autoComplete="off"
          />
        ))}
      </Group>

      <Group legend="How long it may be hired for">
        <TextInput
          {...control('minHireDays')}
          label="Shortest hire, in days"
          inputMode="numeric"
          autoComplete="off"
        />
        <TextInput
          {...control('maxHireDays')}
          label="Longest hire, in days"
          inputMode="numeric"
          autoComplete="off"
        />
      </Group>
    </div>
  )
}
