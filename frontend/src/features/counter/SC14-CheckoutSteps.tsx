/**
 * The first three panels of the SC-14 checkout wizard: tags, condition and
 * accessories. Nothing here is used outside SC-14.
 */

import type { ChangeEvent } from 'react'
import type { ConditionGrade } from '../../shared/types'
import { Field } from '../../shared/ui'
import type { CheckoutRow, ItemDraft } from './SC14-checkout-model'
import { CONDITION_GRADES, CONDITION_LABEL } from './SC14-checkout-model'

/** A checkbox big enough to hit on a phone, with the whole row as target. */
export function CheckRow({
  id,
  checked,
  onChange,
  title,
  detail,
  mono = false,
}: {
  id: string
  checked: boolean
  onChange: (next: boolean) => void
  title: string
  detail?: string
  mono?: boolean
}) {
  return (
    <label
      htmlFor={id}
      className="flex min-h-[2.75rem] cursor-pointer items-start gap-sm rounded border border-line p-sm transition-colors duration-200 hover:bg-muted"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
        className="mt-xs h-5 w-5 shrink-0 cursor-pointer accent-accent"
      />
      <span className="min-w-0">
        <span
          className={`block text-sm font-medium text-ink ${mono ? 'font-mono' : ''}`}
        >
          {title}
        </span>
        {detail && <span className="mt-xs block text-sm text-slate-soft">{detail}</span>}
      </span>
    </label>
  )
}

export function TagStep({
  rows,
  draft,
  onToggle,
}: {
  rows: CheckoutRow[]
  draft: Record<string, ItemDraft>
  onToggle: (itemId: string, next: boolean) => void
}) {
  return (
    <div className="flex flex-col gap-md">
      <p className="text-sm text-slate-soft">
        Read the tag on each unit out loud and tick it off. If a tag does not
        match, stop and fix the allocation before anything leaves the yard.
      </p>
      <div className="flex flex-col gap-sm">
        {rows.map((row) => (
          <CheckRow
            key={row.itemId}
            id={`tag-${row.itemId}`}
            checked={draft[row.itemId].tagConfirmed}
            onChange={(next) => onToggle(row.itemId, next)}
            title={row.tag}
            detail={`${row.manufacturer} ${row.modelName}`}
            mono
          />
        ))}
      </div>
    </div>
  )
}

export function ConditionStep({
  rows,
  draft,
  onChange,
}: {
  rows: CheckoutRow[]
  draft: Record<string, ItemDraft>
  onChange: (itemId: string, patch: Partial<ItemDraft>) => void
}) {
  return (
    <div className="flex flex-col gap-lg">
      <p className="text-sm text-slate-soft">
        Record what the unit looks like as it goes out. This is the reading the
        return inspection is measured against, so a grade written down now
        settles an argument later.
      </p>
      {rows.map((row) => (
        <div key={row.itemId} className="rounded border border-line p-md">
          <p className="font-mono text-sm font-medium text-ink">{row.tag}</p>
          <p className="mb-md text-sm text-slate-soft">
            {row.manufacturer} {row.modelName}, last graded{' '}
            {CONDITION_LABEL[row.conditionOnFile]}
          </p>

          <div className="grid gap-md sm:grid-cols-2">
            <Field label="Condition going out" htmlFor={`cond-${row.itemId}`}>
              <select
                id={`cond-${row.itemId}`}
                className="field-input cursor-pointer"
                value={draft[row.itemId].conditionOut}
                onChange={(e) =>
                  onChange(row.itemId, {
                    conditionOut: e.target.value as ConditionGrade,
                  })
                }
              >
                {CONDITION_GRADES.map((grade) => (
                  <option key={grade} value={grade}>
                    {CONDITION_LABEL[grade]}
                  </option>
                ))}
              </select>
            </Field>

            {row.hasMeter ? (
              <Field
                label="Hour meter reading"
                htmlFor={`meter-${row.itemId}`}
                help={`Last recorded reading, ${row.meterOnFile ?? 0} hours.`}
              >
                <input
                  id={`meter-${row.itemId}`}
                  type="number"
                  inputMode="numeric"
                  min={0}
                  className="field-input tabular"
                  value={draft[row.itemId].meter}
                  onChange={(e) => onChange(row.itemId, { meter: e.target.value })}
                />
              </Field>
            ) : (
              <p className="self-end rounded bg-muted p-sm text-sm text-slate-soft">
                This unit has no hour meter, so there is nothing to read.
              </p>
            )}
          </div>

          <div className="mt-md">
            <Field
              label="Anything worth noting"
              htmlFor={`note-${row.itemId}`}
              help="Optional. Scratches, a missing sticker, a stiff trigger."
            >
              <input
                id={`note-${row.itemId}`}
                type="text"
                className="field-input"
                value={draft[row.itemId].note}
                onChange={(e) => onChange(row.itemId, { note: e.target.value })}
                placeholder="Scuffed housing on the left side"
              />
            </Field>
          </div>
        </div>
      ))}
    </div>
  )
}

export function AccessoryStep({
  accessories,
  checked,
  onToggle,
}: {
  accessories: string[]
  checked: Record<string, boolean>
  onToggle: (item: string, next: boolean) => void
}) {
  return (
    <div className="flex flex-col gap-md">
      <p className="text-sm text-slate-soft">
        Tick what actually goes over the counter. Anything left unticked is not
        handed over, and is not chargeable if it does not come back.
      </p>
      <div className="grid gap-sm sm:grid-cols-2">
        {accessories.map((item, index) => (
          <CheckRow
            key={item}
            id={`acc-${index}`}
            checked={checked[item] ?? false}
            onChange={(next) => onToggle(item, next)}
            title={item}
          />
        ))}
      </div>
    </div>
  )
}
