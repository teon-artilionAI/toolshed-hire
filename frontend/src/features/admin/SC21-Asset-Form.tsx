/**
 * Add or amend one physical unit. Used only by SC-21.
 *
 * The tag is the label physically stuck to the tool, so it is set once when
 * the unit is added and shown but not edited afterwards. Changing it in the
 * system without changing it on the tool is how a unit gets lost.
 */

import { useState } from 'react'
import { Save, X } from 'lucide-react'
import type { Asset, BranchCode, ConditionGrade, ProductModel } from '../../shared/types'
import { branches, TODAY } from '../../shared/fixtures'
import { Field, Notice } from '../../shared/ui'
import { formatDate } from '../../shared/format'

type Draft = Record<string, string>
type Errors = Record<string, string>

const TAG_PATTERN = /^TSH-[A-Z]{2}-\d{4}$/
const CONDITIONS: { grade: ConditionGrade; label: string }[] = [
  { grade: 'A', label: 'A, as new' },
  { grade: 'B', label: 'B, good with light wear' },
  { grade: 'C', label: 'C, serviceable with heavy wear' },
  { grade: 'D', label: 'D, poor and needs attention' },
]

function validate(draft: Draft, takenTags: string[], creating: boolean): Errors {
  const errors: Errors = {}

  if (creating) {
    const tag = draft.tag.trim().toUpperCase()
    if (!tag) errors.tag = 'Enter the tag printed on the unit, for example TSH-DR-0042.'
    else if (!TAG_PATTERN.test(tag)) {
      errors.tag = 'Tags look like TSH-DR-0042: three letters, two letters for the tool type, then four digits.'
    } else if (takenTags.includes(tag)) {
      errors.tag = `${tag} is already on another unit. Check the label and enter the tag you are holding.`
    }
    if (!draft.productModelId) errors.productModelId = 'Choose which tool this unit is.'
  }

  if (!draft.acquiredOn) {
    errors.acquiredOn = 'Enter the date the unit was bought.'
  } else if (new Date(draft.acquiredOn) > new Date(TODAY)) {
    errors.acquiredOn = `That date is in the future. Today is ${formatDate(TODAY)}.`
  }

  const cost = Number(draft.acquisitionCost)
  if (draft.acquisitionCost.trim() === '' || Number.isNaN(cost)) {
    errors.acquisitionCost = 'Enter what the unit cost, in rand.'
  } else if (cost <= 0) {
    errors.acquisitionCost = 'The purchase price must be more than R0.00.'
  }

  if (draft.meterHours.trim() !== '') {
    const hours = Number(draft.meterHours)
    if (Number.isNaN(hours) || hours < 0) {
      errors.meterHours = 'Enter the hours shown on the meter, or leave it empty if the unit has no meter.'
    }
  }
  return errors
}

export default function AssetForm({
  asset, models, takenTags, onSave, onCancel,
}: {
  /** The unit being amended, or undefined when adding a new one. */
  asset?: Asset
  models: ProductModel[]
  /** Tags already in use, upper cased. */
  takenTags: string[]
  onSave: (asset: Asset) => void
  onCancel: () => void
}) {
  const creating = asset === undefined
  const [draft, setDraft] = useState<Draft>(() => ({
    productModelId: asset?.productModelId ?? models[0]?.id ?? '',
    tag: asset?.tag ?? '',
    branchCode: asset?.branchCode ?? 'CBD',
    condition: asset?.condition ?? 'A',
    acquiredOn: asset?.acquiredOn ?? TODAY,
    acquisitionCost: asset ? String(asset.acquisitionCost) : '',
    meterHours: asset?.meterHours === undefined ? '' : String(asset.meterHours),
  }))
  const [errors, setErrors] = useState<Errors>({})
  const [tried, setTried] = useState(false)

  const onHire = asset?.status === 'ON_HIRE'
  const change = (key: string, value: string) => {
    const next = { ...draft, [key]: value }
    setDraft(next)
    if (tried) setErrors(validate(next, takenTags, creating))
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    setTried(true)
    const found = validate(draft, takenTags, creating)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    onSave({
      id: asset?.id ?? `as-new-${draft.tag.trim().toUpperCase()}`,
      productModelId: draft.productModelId,
      tag: creating ? draft.tag.trim().toUpperCase() : (asset?.tag ?? ''),
      branchCode: draft.branchCode as BranchCode,
      status: asset?.status ?? 'AVAILABLE',
      condition: draft.condition as ConditionGrade,
      acquiredOn: draft.acquiredOn,
      acquisitionCost: Number(draft.acquisitionCost),
      meterHours: draft.meterHours.trim() === '' ? undefined : Number(draft.meterHours),
    })
  }

  const problems = Object.keys(errors).length

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-md">
      {tried && problems > 0 && (
        <Notice tone="error" title="Nothing has been saved yet">
          <p>
            There {problems === 1 ? 'is one thing' : `are ${problems} things`} to put right first.
            Each one is marked below the field it belongs to.
          </p>
        </Notice>
      )}
      {onHire && (
        <Notice tone="warn" title="This unit is out with a customer">
          <p>
            You can correct its details, but leave the branch alone until it is back. Moving it now
            would send the counter looking in the wrong yard.
          </p>
        </Notice>
      )}

      <div className="grid gap-md sm:grid-cols-2">
        {creating ? (
          <Field label="Which tool is it" htmlFor="productModelId" error={errors.productModelId}>
            <select
              id="productModelId" className="field-input" value={draft.productModelId}
              onChange={(e) => change('productModelId', e.target.value)}
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>{m.manufacturer} {m.name}</option>
              ))}
            </select>
          </Field>
        ) : (
          <Field label="Tool" htmlFor="model-fixed" help="A unit cannot become a different tool. Add a new unit instead.">
            <input
              id="model-fixed" className="field-input" readOnly
              value={models.find((m) => m.id === draft.productModelId)?.name ?? 'Unknown'}
              aria-describedby="model-fixed-help"
            />
          </Field>
        )}

        {creating ? (
          <Field label="Asset tag" htmlFor="tag" help="The label stuck to the tool itself." error={errors.tag}>
            <input
              id="tag" className="field-input font-mono uppercase" value={draft.tag}
              placeholder="TSH-DR-0047"
              aria-invalid={errors.tag ? true : undefined}
              aria-describedby={errors.tag ? 'tag-error' : 'tag-help'}
              onChange={(e) => change('tag', e.target.value)}
            />
          </Field>
        ) : (
          <Field label="Asset tag" htmlFor="tag-fixed" help="Set when the unit was added, because it is printed on the tool.">
            <input
              id="tag-fixed" className="field-input font-mono" readOnly value={asset?.tag ?? ''}
              aria-describedby="tag-fixed-help"
            />
          </Field>
        )}

        <Field label="Branch it lives at" htmlFor="branchCode" error={errors.branchCode}>
          <select
            id="branchCode" className="field-input" value={draft.branchCode} disabled={onHire}
            onChange={(e) => change('branchCode', e.target.value)}
          >
            {branches.map((b) => (
              <option key={b.code} value={b.code}>{b.name}</option>
            ))}
          </select>
        </Field>

        <Field label="Condition grade" htmlFor="condition">
          <select
            id="condition" className="field-input" value={draft.condition}
            onChange={(e) => change('condition', e.target.value)}
          >
            {CONDITIONS.map((c) => (
              <option key={c.grade} value={c.grade}>{c.label}</option>
            ))}
          </select>
        </Field>

        <Field label="Bought on" htmlFor="acquiredOn" error={errors.acquiredOn}>
          <input
            id="acquiredOn" type="date" className="field-input" value={draft.acquiredOn} max={TODAY}
            aria-invalid={errors.acquiredOn ? true : undefined}
            aria-describedby={errors.acquiredOn ? 'acquiredOn-error' : undefined}
            onChange={(e) => change('acquiredOn', e.target.value)}
          />
        </Field>

        <Field label="Purchase price" htmlFor="acquisitionCost" help="What we paid, in rand." error={errors.acquisitionCost}>
          <input
            id="acquisitionCost" type="number" min={0} step={50} inputMode="decimal"
            className="field-input tabular" value={draft.acquisitionCost}
            aria-invalid={errors.acquisitionCost ? true : undefined}
            aria-describedby={errors.acquisitionCost ? 'acquisitionCost-error' : 'acquisitionCost-help'}
            onChange={(e) => change('acquisitionCost', e.target.value)}
          />
        </Field>

        <Field label="Meter hours" htmlFor="meterHours" help="Leave empty if the unit has no hour meter." error={errors.meterHours}>
          <input
            id="meterHours" type="number" min={0} step={1} inputMode="numeric"
            className="field-input tabular" value={draft.meterHours}
            aria-invalid={errors.meterHours ? true : undefined}
            aria-describedby={errors.meterHours ? 'meterHours-error' : 'meterHours-help'}
            onChange={(e) => change('meterHours', e.target.value)}
          />
        </Field>
      </div>

      <div className="flex flex-wrap gap-sm">
        <button type="submit" className="btn-primary px-md">
          <Save className="h-4 w-4 shrink-0" aria-hidden="true" />
          {creating ? 'Add this unit' : 'Save these changes'}
        </button>
        <button type="button" className="btn-secondary px-md" onClick={onCancel}>
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          Cancel
        </button>
      </div>
    </form>
  )
}
