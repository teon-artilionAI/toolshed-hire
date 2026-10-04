/**
 * The categories on SC-20, from `GET /api/admin/categories`.
 *
 * Every category is listed, switched on or off, each parent before its
 * children the way the server sends them. The owner adds one or changes one
 * in the form above the list, and switches one off or on from its row. A
 * category is never deleted. Each write asks first, and the list is read again
 * once the server has answered.
 *
 * It has the shared loading, failed and empty states. The form's heading
 * takes focus when it opens, and closing it unsaved gives focus back to the
 * button that opened it.
 */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Plus } from 'lucide-react'
import type { AdminCategory, AdminCategoryList } from '../../shared/api/contract'
import type { QueryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { EmptyState } from '../../shared/ui'
import { countOf } from '../counter/counter-labels'
import { CategoryForm } from './SC20-Category-Form'
import CategoryTable from './SC20-Category-Table'

/** What the screen says once a category write has worked. */
export interface CategoryOutcome {
  title: string
  body: string
}

/** Which category the form has open. */
type Editing = { kind: 'new' } | { kind: 'change'; category: AdminCategory }

const FORM_HEADING_ID = 'category-form-heading'
const SKELETON_ROWS = 2

function FormFrame({ title, children }: { title: string; children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  return (
    <section aria-labelledby={FORM_HEADING_ID} className="mb-lg min-w-0 rounded-lg border border-line p-md">
      <h3 id={FORM_HEADING_ID} ref={heading} tabIndex={-1} className="mb-md break-words text-base font-semibold text-ink">
        {title}
      </h3>
      {children}
    </section>
  )
}

export default function CategoryManager({
  list,
  phase,
  error,
  onRetry,
  onDone,
}: {
  /** The categories once they have been read. */
  list: AdminCategoryList | undefined
  /** Where the read of the categories stands. */
  phase: QueryPhase
  /** Why the last read failed, when it did. */
  error: unknown
  onRetry: () => void
  onDone: (outcome: CategoryOutcome) => void
}) {
  const [editing, setEditing] = useState<Editing | null>(null)
  const [askingId, setAskingId] = useState<string | null>(null)
  const addButton = useRef<HTMLButtonElement>(null)

  function closeForm() {
    setEditing(null)
    addButton.current?.focus()
  }

  function saved(category: AdminCategory, wasNew: boolean) {
    setEditing(null)
    onDone({
      title: wasNew ? `${category.name} is added to the categories` : `${category.name} is saved`,
      body: category.parentName === null ? 'It sits at the top level.' : `It sits under ${category.parentName}.`,
    })
  }

  function switched(category: AdminCategory) {
    setAskingId(null)
    onDone({
      title: category.isActive ? `${category.name} is switched on` : `${category.name} is switched off`,
      body: category.isActive
        ? 'It is back in the catalogue customers browse.'
        : 'It has left the catalogue customers browse. Nothing in it was deleted.',
    })
  }

  return (
    <section aria-labelledby="categories-heading" className="card min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-md border-b border-line px-lg py-md">
        <h2 id="categories-heading" className="text-sm font-semibold uppercase tracking-wide text-slate-soft">
          Categories
        </h2>
        <button ref={addButton} type="button" className="btn-secondary px-md" onClick={() => setEditing({ kind: 'new' })}>
          <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
          Add a category
        </button>
      </div>
      <div className="p-lg">
        {editing !== null && list !== undefined && (
          <FormFrame title={editing.kind === 'new' ? 'Add a category' : `Change the category ${editing.category.name}`}>
            <CategoryForm
              key={editing.kind === 'new' ? 'new' : editing.category.id}
              category={editing.kind === 'new' ? null : editing.category}
              categories={list.items}
              onSaved={(category) => saved(category, editing.kind === 'new')}
              onClose={closeForm}
            />
          </FormFrame>
        )}
        <p role="status" className="mb-md text-sm text-slate-soft">
          {phase === 'ready' && list !== undefined
            ? `${countOf(list.total, 'category', 'categories')}, switched on or off. Customers see only the ones switched on.`
            : phase === 'loading'
              ? 'Loading the categories.'
              : ''}
        </p>
        {phase === 'failed' ? (
          <ErrorState what="the categories" error={error} onRetry={onRetry} />
        ) : list === undefined ? (
          <LoadingState shape="rows" count={SKELETON_ROWS} />
        ) : list.items.length === 0 ? (
          <EmptyState
            title="There are no categories yet"
            body="Add the first category, then put models in it."
            action={
              <button type="button" className="btn-secondary px-md" onClick={() => setEditing({ kind: 'new' })}>
                Add a category
              </button>
            }
          />
        ) : (
          <CategoryTable
            categories={list.items}
            askingId={askingId}
            onEdit={(category) => setEditing({ kind: 'change', category })}
            onAsk={(category) => setAskingId(category.id)}
            onCancel={() => setAskingId(null)}
            onSwitched={switched}
          />
        )}
      </div>
    </section>
  )
}
