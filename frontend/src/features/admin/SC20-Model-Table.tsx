/**
 * One page of the models on SC-20, as a table.
 *
 * Each model shows its name and stock code, its category, how many units the
 * fleet holds, the daily rate with the weekly rate under it, the deposit, the
 * late fee and the replacement value, and whether customers see it, in words
 * beside its colour. Every figure is the server's, in the order the server
 * sent the models. Nothing is summed or worked out.
 *
 * Nine columns do not fit across a phone, so below the `lg` width each model
 * is drawn as a block with every value on a line of its own and the name of
 * its column beside it. It is the same table either way, and each part states
 * its role, because changing how a table is displayed can make a browser stop
 * reporting it as one.
 *
 * "Publish" and "Hide" open their question in a row of its own under the
 * model. Closing it gives focus back to the button that opened it.
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Eye, EyeOff, Pencil } from 'lucide-react'
import type { AdminModel } from '../../shared/api/contract'
import { money } from '../../shared/format'
import { StatusPill } from '../../shared/ui'
import { editModelButtonId, publicationPill } from './catalogue-labels'
import { MONEY_LABEL } from './model-form'
import { PublicationQuestion } from './SC20-Publication'

const COLUMNS = [
  'Model',
  'Category',
  'Units',
  MONEY_LABEL.dailyRate,
  MONEY_LABEL.depositAmount,
  MONEY_LABEL.lateFeePerDay,
  MONEY_LABEL.replacementValue,
  'Shown to customers',
  'Actions',
] as const

/** What every cell shares. A table cell from `lg` up, and a line of a block below it. */
const CELL_BASE = 'td px-0 py-xs text-left lg:table-cell lg:px-md lg:py-sm'

/** A cell that shows the name of its column beside its value below `lg`. */
const LABELLED_CELL = `${CELL_BASE} flex items-baseline justify-between gap-md`

function ColumnName({ children }: { children: ReactNode }) {
  return <span className="shrink-0 text-sm text-slate-soft lg:hidden">{children}</span>
}

function Figure({ column, children }: { column: string; children: ReactNode }) {
  return (
    <td role="cell" className={LABELLED_CELL}>
      <ColumnName>{column}</ColumnName>
      <span className="tabular min-w-0 text-right text-ink lg:text-left">{children}</span>
    </td>
  )
}

function ModelRow({
  model,
  asking,
  onEdit,
  onAsk,
  onCancel,
  onPublication,
}: {
  model: AdminModel
  asking: boolean
  onEdit: (model: AdminModel) => void
  onAsk: (model: AdminModel) => void
  onCancel: () => void
  onPublication: (model: AdminModel, published: boolean) => void
}) {
  const askButton = useRef<HTMLButtonElement>(null)
  // Set when the question is put away unanswered, so focus goes back to the
  // button that opened it once that button is on the page again.
  const giveFocusBack = useRef(false)
  useEffect(() => {
    if (asking || !giveFocusBack.current) return
    giveFocusBack.current = false
    askButton.current?.focus()
  }, [asking])
  const pill = publicationPill(model.isPublished)
  return (
    <>
      <tr role="row" className="block px-md py-sm lg:table-row">
        <th role="rowheader" scope="row" className={`${CELL_BASE} block font-medium text-ink`}>
          <span className="block break-words">{model.name}</span>
          <span className="mt-xs block break-all font-mono text-xs font-normal text-slate-soft">{model.sku}</span>
        </th>
        <Figure column="Category">
          <span className="break-words">{model.categoryName}</span>
        </Figure>
        <Figure column="Units">{String(model.assetCount)}</Figure>
        <Figure column={MONEY_LABEL.dailyRate}>
          {money(model.dailyRate)}
          <span className="block text-xs text-slate-soft">{money(model.weeklyRate)} a week</span>
        </Figure>
        <Figure column={MONEY_LABEL.depositAmount}>{money(model.depositAmount)}</Figure>
        <Figure column={MONEY_LABEL.lateFeePerDay}>{money(model.lateFeePerDay)}</Figure>
        <Figure column={MONEY_LABEL.replacementValue}>{money(model.replacementValue)}</Figure>
        <td role="cell" className={LABELLED_CELL}>
          <ColumnName>Shown to customers</ColumnName>
          <StatusPill status={pill.status} label={pill.label} />
        </td>
        <td role="cell" className={`${CELL_BASE} block pt-sm`}>
          <div className="flex flex-wrap gap-sm">
            <button
              id={editModelButtonId(model.id)}
              type="button"
              className="btn-secondary px-md"
              onClick={() => onEdit(model)}
            >
              <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
              Edit{' '}
              <span className="sr-only">{model.name}</span>
            </button>
            {!asking && (
              <button ref={askButton} type="button" className="btn-secondary px-md" onClick={() => onAsk(model)}>
                {model.isPublished ? (
                  <EyeOff className="h-4 w-4 shrink-0" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4 shrink-0" aria-hidden="true" />
                )}
                {model.isPublished ? 'Hide' : 'Publish'}{' '}
                <span className="sr-only">{model.name}</span>
              </button>
            )}
          </div>
        </td>
      </tr>
      {asking && (
        <tr role="row" className="block lg:table-row">
          <td role="cell" colSpan={COLUMNS.length} className="block px-md pb-md lg:table-cell">
            <PublicationQuestion
              model={model}
              onDone={(published) => onPublication(model, published)}
              onCancel={() => {
                giveFocusBack.current = true
                onCancel()
              }}
            />
          </td>
        </tr>
      )}
    </>
  )
}

export default function ModelTable({
  models,
  askingId,
  onEdit,
  onAsk,
  onCancel,
  onPublication,
}: {
  models: readonly AdminModel[]
  /** The model whose publication question is open, or null. */
  askingId: string | null
  onEdit: (model: AdminModel) => void
  onAsk: (model: AdminModel) => void
  onCancel: () => void
  onPublication: (model: AdminModel, published: boolean) => void
}) {
  return (
    <div className="table-wrap">
      <table role="table" className="block w-full border-collapse lg:table">
        <caption className="sr-only">
          Each model with its category, its units, its daily rate, deposit, late fee and replacement value, and
          whether customers see it.
        </caption>
        <thead role="rowgroup" className="hidden border-b border-line bg-muted lg:table-header-group">
          <tr role="row">
            {COLUMNS.map((heading) => (
              <th key={heading} role="columnheader" scope="col" className="th whitespace-normal">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block divide-y divide-line lg:table-row-group">
          {models.map((model) => (
            <ModelRow
              key={model.id}
              model={model}
              asking={askingId === model.id}
              onEdit={onEdit}
              onAsk={onAsk}
              onCancel={onCancel}
              onPublication={onPublication}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
