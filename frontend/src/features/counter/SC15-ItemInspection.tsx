/**
 * One unit being inspected on its way back in, for SC-15.
 *
 * The condition coming back sits next to the condition that went out, because
 * the only question that matters at a return counter is whether those two
 * differ. When they do, the screen says so in words and offers the damage
 * report rather than waiting for the assistant to remember.
 */

import { Link } from 'react-router-dom'
import { CheckCircle2, TriangleAlert } from 'lucide-react'
import type { ConditionGrade } from '../../shared/types'
import { Notice, StatusPill } from '../../shared/ui'
import { CONDITION_GRADES, CONDITION_LABEL } from './SC14-checkout-model'
import type { ReturnDraft, ReturnRow } from './SC15-return-model'
import { isWorse } from './SC15-return-model'

export function ItemInspection({
  row,
  draft,
  onChange,
}: {
  row: ReturnRow
  draft: ReturnDraft
  onChange: (next: Partial<ReturnDraft>) => void
}) {
  const worse = isWorse(draft.conditionIn, row.conditionOut)
  const hoursUsed = Math.max(
    0,
    (Number.parseFloat(draft.meterIn) || 0) - (row.meterOut ?? 0),
  )

  return (
    <div className="rounded border border-line p-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <p className="font-mono text-sm font-medium text-ink">{row.tag}</p>
        <StatusPill
          status={draft.received ? 'RETURNED' : 'OPEN'}
          label={draft.received ? 'Received' : 'Still out'}
        />
      </div>
      <p className="mb-md text-sm text-slate-soft">
        {row.manufacturer} {row.modelName}, out at {CONDITION_LABEL[row.conditionOut]}
        {row.hasMeter && `, ${row.meterOut} hours on the meter`}.
      </p>

      <label
        htmlFor={`received-${row.itemId}`}
        className="mb-md flex min-h-[2.75rem] cursor-pointer items-center gap-sm rounded border border-line p-sm transition-colors duration-200 hover:bg-muted"
      >
        <input
          id={`received-${row.itemId}`}
          type="checkbox"
          checked={draft.received}
          onChange={(e) => onChange({ received: e.target.checked })}
          className="h-5 w-5 shrink-0 cursor-pointer accent-accent"
        />
        <span className="text-sm font-medium text-ink">
          This unit is physically back on the counter
        </span>
      </label>

      <div className="grid gap-md sm:grid-cols-2">
        <div>
          <label className="field-label" htmlFor={`in-${row.itemId}`}>
            Condition coming back
          </label>
          <select
            id={`in-${row.itemId}`}
            className="field-input cursor-pointer"
            value={draft.conditionIn}
            onChange={(e) => onChange({ conditionIn: e.target.value as ConditionGrade })}
          >
            {CONDITION_GRADES.map((grade) => (
              <option key={grade} value={grade}>
                {CONDITION_LABEL[grade]}
              </option>
            ))}
          </select>
          <p className="field-help">Out at {CONDITION_LABEL[row.conditionOut]}.</p>
        </div>

        {row.hasMeter && (
          <div>
            <label className="field-label" htmlFor={`meterin-${row.itemId}`}>
              Hour meter reading now
            </label>
            <input
              id={`meterin-${row.itemId}`}
              type="number"
              inputMode="numeric"
              min={row.meterOut ?? 0}
              className="field-input tabular"
              value={draft.meterIn}
              onChange={(e) => onChange({ meterIn: e.target.value })}
            />
            <p className="field-help">
              Out at {row.meterOut} hours. Hours used on this hire: {hoursUsed}.
            </p>
          </div>
        )}
      </div>

      {worse && (
        <div className="mt-md flex flex-col gap-sm">
          <Notice tone="warn" title="This unit has come back worse than it went out">
            Out at {CONDITION_LABEL[row.conditionOut]}, back at{' '}
            {CONDITION_LABEL[draft.conditionIn]}. Raise a damage report so the
            workshop picks it up, and charge the repair here if it is the
            customer's to pay.
          </Notice>
          <div className="flex flex-wrap items-end gap-md">
            <Link to={`/counter/damage/${row.assetId}`} className="btn-secondary px-md">
              <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
              Raise a damage report
            </Link>
            <div className="min-w-[12rem] flex-1">
              <label className="field-label" htmlFor={`damage-${row.itemId}`}>
                Damage to charge, in rand
              </label>
              <input
                id={`damage-${row.itemId}`}
                type="number"
                inputMode="decimal"
                min={0}
                className="field-input tabular"
                value={draft.damageCharge}
                placeholder="0.00"
                onChange={(e) =>
                  onChange({ damageCharge: e.target.value, chargeDamage: true })
                }
              />
              <p className="field-help">Leave blank if the repair is not chargeable.</p>
            </div>
          </div>
        </div>
      )}

      {draft.received && !worse && (
        <p className="mt-md flex items-center gap-xs text-sm text-status-available">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Back in the same condition it went out.
        </p>
      )}
    </div>
  )
}
