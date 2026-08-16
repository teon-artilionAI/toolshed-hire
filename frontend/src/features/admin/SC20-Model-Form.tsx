/**
 * The edit form for one catalogue entry, used only by SC-20.
 *
 * Pricing is the part of this system that quietly loses money, so the
 * validation is about business sense rather than about types. A late fee
 * above the daily rate, or a deposit worth more than the tool it covers,
 * is accepted by any number field and is wrong every time.
 */

import { useState } from 'react'
import { Save, X } from 'lucide-react'
import type { Category, ProductModel } from '../../shared/types'
import { Field, Notice } from '../../shared/ui'
import { money } from '../../shared/format'

type Draft = Record<string, string>
type Errors = Record<string, string>

const MONEY_FIELDS = ['dailyRate', 'depositAmount', 'lateFeePerDay', 'replacementValue']

function toDraft(model: ProductModel): Draft {
  return {
    name: model.name,
    manufacturer: model.manufacturer,
    sku: model.sku,
    categoryId: model.categoryId,
    description: model.description,
    dailyRate: String(model.dailyRate),
    depositAmount: String(model.depositAmount),
    lateFeePerDay: String(model.lateFeePerDay),
    replacementValue: String(model.replacementValue),
  }
}

function validate(draft: Draft, takenSkus: string[]): Errors {
  const errors: Errors = {}
  if (!draft.name.trim()) errors.name = 'Give the tool a name, as a customer would search for it.'
  if (!draft.manufacturer.trim()) errors.manufacturer = 'Name the manufacturer, for example Bosch or Stihl.'

  const sku = draft.sku.trim()
  if (!sku) errors.sku = 'A stock code is required. Ours look like TSH-PM-0101.'
  else if (takenSkus.includes(sku.toUpperCase())) {
    errors.sku = `${sku} is already used by another entry. Give this one its own code.`
  }

  for (const key of MONEY_FIELDS) {
    const value = Number(draft[key])
    if (draft[key].trim() === '' || Number.isNaN(value)) {
      errors[key] = 'Enter an amount in rand, digits only.'
    } else if (value < 0) {
      errors[key] = 'An amount cannot be less than zero.'
    }
  }

  const rate = Number(draft.dailyRate)
  const late = Number(draft.lateFeePerDay)
  const deposit = Number(draft.depositAmount)
  const replacement = Number(draft.replacementValue)

  if (!errors.dailyRate && rate <= 0) {
    errors.dailyRate = 'The daily rate must be more than R0.00, or the tool hires out for nothing.'
  }
  if (!errors.lateFeePerDay && !errors.dailyRate && late > rate) {
    errors.lateFeePerDay = `A late fee of ${money(late)} is more than the ${money(rate)} daily rate. Bring it down to the rate or below.`
  }
  if (!errors.replacementValue && replacement <= 0) {
    errors.replacementValue = 'Record what it costs to replace the tool. This is what a write off is measured against.'
  }
  if (!errors.depositAmount && !errors.replacementValue && deposit > replacement) {
    errors.depositAmount = `A deposit of ${money(deposit)} is more than the ${money(replacement)} replacement value. Customers will not pay more than the tool is worth.`
  }
  return errors
}

function MoneyField({
  id, label, help, draft, errors, onChange,
}: {
  id: string
  label: string
  help: string
  draft: Draft
  errors: Errors
  onChange: (key: string, value: string) => void
}) {
  return (
    <Field label={label} htmlFor={id} help={help} error={errors[id]}>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        step={5}
        className="field-input tabular"
        value={draft[id]}
        aria-invalid={errors[id] ? true : undefined}
        aria-describedby={errors[id] ? `${id}-error` : `${id}-help`}
        onChange={(e) => onChange(id, e.target.value)}
      />
    </Field>
  )
}

export default function ModelForm({
  model, categories, takenSkus, onSave, onCancel,
}: {
  model: ProductModel
  categories: Category[]
  /** Stock codes already in use by other entries, upper cased. */
  takenSkus: string[]
  onSave: (updated: ProductModel) => void
  onCancel: () => void
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(model))
  const [errors, setErrors] = useState<Errors>({})
  const [tried, setTried] = useState(false)

  const change = (key: string, value: string) => {
    const next = { ...draft, [key]: value }
    setDraft(next)
    if (tried) setErrors(validate(next, takenSkus))
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    setTried(true)
    const found = validate(draft, takenSkus)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    onSave({
      ...model,
      name: draft.name.trim(),
      manufacturer: draft.manufacturer.trim(),
      sku: draft.sku.trim(),
      categoryId: draft.categoryId,
      description: draft.description.trim(),
      dailyRate: Number(draft.dailyRate),
      depositAmount: Number(draft.depositAmount),
      lateFeePerDay: Number(draft.lateFeePerDay),
      replacementValue: Number(draft.replacementValue),
    })
  }

  const problems = Object.values(errors)

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-md">
      {tried && problems.length > 0 && (
        <Notice tone="error" title="Nothing has been saved yet">
          <p>
            There {problems.length === 1 ? 'is one thing' : `are ${problems.length} things`} to put
            right first. Each one is marked below the field it belongs to.
          </p>
        </Notice>
      )}

      <div className="grid gap-md sm:grid-cols-2">
        <Field label="Tool name" htmlFor="name" error={errors.name}>
          <input
            id="name" className="field-input" value={draft.name}
            aria-invalid={errors.name ? true : undefined}
            aria-describedby={errors.name ? 'name-error' : undefined}
            onChange={(e) => change('name', e.target.value)}
          />
        </Field>
        <Field label="Manufacturer" htmlFor="manufacturer" error={errors.manufacturer}>
          <input
            id="manufacturer" className="field-input" value={draft.manufacturer}
            aria-invalid={errors.manufacturer ? true : undefined}
            aria-describedby={errors.manufacturer ? 'manufacturer-error' : undefined}
            onChange={(e) => change('manufacturer', e.target.value)}
          />
        </Field>
        <Field label="Stock code" htmlFor="sku" help="Printed on the shelf label." error={errors.sku}>
          <input
            id="sku" className="field-input font-mono" value={draft.sku}
            aria-invalid={errors.sku ? true : undefined}
            aria-describedby={errors.sku ? 'sku-error' : 'sku-help'}
            onChange={(e) => change('sku', e.target.value)}
          />
        </Field>
        <Field label="Category" htmlFor="categoryId">
          <select
            id="categoryId" className="field-input" value={draft.categoryId}
            onChange={(e) => change('categoryId', e.target.value)}
          >
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </Field>
      </div>

      <div className="grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <MoneyField
          id="dailyRate" label="Daily hire rate" help="What one unit costs per day."
          draft={draft} errors={errors} onChange={change}
        />
        <MoneyField
          id="depositAmount" label="Deposit" help="Held at collection, released at return."
          draft={draft} errors={errors} onChange={change}
        />
        <MoneyField
          id="lateFeePerDay" label="Late fee per day" help="Charged for each day past the due date."
          draft={draft} errors={errors} onChange={change}
        />
        <MoneyField
          id="replacementValue" label="Replacement value" help="What it costs us to buy another one."
          draft={draft} errors={errors} onChange={change}
        />
      </div>

      <Field
        label="Description"
        htmlFor="description"
        help="What customers read on the catalogue page. Say what the tool is for."
      >
        <textarea
          id="description" rows={3} className="field-input" value={draft.description}
          aria-describedby="description-help"
          onChange={(e) => change('description', e.target.value)}
        />
      </Field>

      <div className="flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md">
          <Save className="h-4 w-4 shrink-0" aria-hidden="true" />
          Save these changes
        </button>
        <button type="button" className="btn-secondary px-md" onClick={onCancel}>
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          Cancel
        </button>
      </div>
    </form>
  )
}
