/**
 * The categories on SC-20, as a table, each parent before its children the
 * way the server lists them.
 *
 * Each category shows its name and code, what it sits under, its place in the
 * list, how many models it holds and whether it is switched on, in words
 * beside its colour. Below the `lg` width each one is drawn as a block with
 * every value beside the name of its column, and it is the same table either
 * way.
 *
 * "Switch off" and "Switch on" open their question in a row of its own under
 * the category, and send `isActive` once it is answered. Nothing is deleted. A
 * category switched off leaves the catalogue customers browse and can be
 * switched on again. Closing the question unanswered gives focus back to the
 * button that opened it.
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Pencil, Power } from 'lucide-react'
import { changeCategory } from '../../shared/api/admin-catalogue'
import type { AdminCategory } from '../../shared/api/contract'
import { StatusPill } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { categoryPill } from './catalogue-labels'
import { WriteQuestion } from './SC20-Write-Question'
import { useCatalogueWrite } from './use-catalogue-write'

const COLUMNS = ['Category', 'Sits under', 'Place in the list', 'Models', 'State', 'Actions'] as const

/** What every cell shares. A table cell from `lg` up, and a line of a block below it. */
const CELL_BASE = 'td px-0 py-xs text-left lg:table-cell lg:px-md lg:py-sm'

/** A cell that shows the name of its column beside its value below `lg`. */
const LABELLED_CELL = `${CELL_BASE} flex items-baseline justify-between gap-md`

function Value({ column, children }: { column: string; children: ReactNode }) {
  return (
    <td role="cell" className={LABELLED_CELL}>
      <span className="shrink-0 text-sm text-slate-soft lg:hidden">{column}</span>
      <span className="tabular min-w-0 break-words text-right text-ink lg:text-left">{children}</span>
    </td>
  )
}

function SwitchQuestion({
  category,
  onDone,
  onCancel,
}: {
  category: AdminCategory
  onDone: (saved: AdminCategory) => void
  onCancel: () => void
}) {
  const write = useCatalogueWrite('category_switched', category.id)
  const switchingOn = !category.isActive
  const models = countOf(category.modelCount, 'model', 'models')
  return (
    <WriteQuestion
      id={`switch-${category.id}`}
      heading={switchingOn ? `Switch ${category.name} on?` : `Switch ${category.name} off?`}
      answer={switchingOn ? 'Yes, switch it on' : 'Yes, switch it off'}
      pendingAnswer={switchingOn ? 'Switching it on' : 'Switching it off'}
      cancel="Keep it as it is"
      refusedTitle={switchingOn ? 'The category was not switched on' : 'The category was not switched off'}
      pending={write.pending}
      failure={write.failure}
      onAnswer={() => write.send(() => changeCategory(category.id, { isActive: switchingOn }), { onAnswer: onDone })}
      onCancel={() => {
        write.clearFailure()
        onCancel()
      }}
    >
      {switchingOn ? (
        <p>It goes back into the catalogue customers browse, and models can be put in it again.</p>
      ) : (
        <p>
          It leaves the catalogue customers browse, and no model can be put in it while it is off. Nothing is
          deleted, and the {models} in it stay where they are.
        </p>
      )}
    </WriteQuestion>
  )
}

function CategoryRow({
  category,
  asking,
  onEdit,
  onAsk,
  onCancel,
  onSwitched,
}: {
  category: AdminCategory
  asking: boolean
  onEdit: (category: AdminCategory) => void
  onAsk: (category: AdminCategory) => void
  onCancel: () => void
  onSwitched: (saved: AdminCategory) => void
}) {
  const askButton = useRef<HTMLButtonElement>(null)
  const giveFocusBack = useRef(false)
  useEffect(() => {
    if (asking || !giveFocusBack.current) return
    giveFocusBack.current = false
    askButton.current?.focus()
  }, [asking])
  const pill = categoryPill(category.isActive)
  const child = category.parentCategoryId !== null
  return (
    <>
      <tr role="row" className="block px-md py-sm lg:table-row">
        <th role="rowheader" scope="row" className={`${CELL_BASE} block font-medium text-ink ${child ? 'lg:pl-xl' : ''}`}>
          <span className="block break-words">{category.name}</span>
          <span className="mt-xs block break-all font-mono text-xs font-normal text-slate-soft">{category.code}</span>
        </th>
        <Value column="Sits under">{category.parentName ?? 'Top level'}</Value>
        <Value column="Place in the list">{String(category.sortOrder)}</Value>
        <Value column="Models">{String(category.modelCount)}</Value>
        <td role="cell" className={LABELLED_CELL}>
          <span className="shrink-0 text-sm text-slate-soft lg:hidden">State</span>
          <StatusPill status={pill.status} label={pill.label} />
        </td>
        <td role="cell" className={`${CELL_BASE} block pt-sm`}>
          <div className="flex flex-wrap gap-sm">
            <button type="button" className="btn-secondary px-md" onClick={() => onEdit(category)}>
              <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
              Edit{' '}
              <span className="sr-only">the category {category.name}</span>
            </button>
            {!asking && (
              <button ref={askButton} type="button" className="btn-secondary px-md" onClick={() => onAsk(category)}>
                <Power className="h-4 w-4 shrink-0" aria-hidden="true" />
                {category.isActive ? 'Switch off' : 'Switch on'}{' '}
                <span className="sr-only">{category.name}</span>
              </button>
            )}
          </div>
        </td>
      </tr>
      {asking && (
        <tr role="row" className="block lg:table-row">
          <td role="cell" colSpan={COLUMNS.length} className="block px-md pb-md lg:table-cell">
            <SwitchQuestion
              category={category}
              onDone={onSwitched}
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

export default function CategoryTable({
  categories,
  askingId,
  onEdit,
  onAsk,
  onCancel,
  onSwitched,
}: {
  categories: readonly AdminCategory[]
  /** The category whose question is open, or null. */
  askingId: string | null
  onEdit: (category: AdminCategory) => void
  onAsk: (category: AdminCategory) => void
  onCancel: () => void
  onSwitched: (saved: AdminCategory) => void
}) {
  return (
    <div className="table-wrap">
      <table role="table" className="block w-full border-collapse lg:table">
        <caption className="sr-only">
          Every category, switched on or off, each with what it sits under, its place in the list and its models.
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
          {categories.map((category) => (
            <CategoryRow
              key={category.id}
              category={category}
              asking={askingId === category.id}
              onEdit={onEdit}
              onAsk={onAsk}
              onCancel={onCancel}
              onSwitched={onSwitched}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
