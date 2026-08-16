/**
 * The category list on SC-20.
 *
 * Categories are how customers narrow a catalogue of a hundred and twenty
 * tools down to the four they might want, so an empty one is worse than
 * none. A category can only be removed once nothing sits in it, and the
 * screen says so before you reach for the button rather than after.
 */

import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import type { Category } from '../../shared/types'
import { Field } from '../../shared/ui'

export default function CategoryManager({
  categories, countFor, onAdd, onRemove,
}: {
  categories: Category[]
  /** How many catalogue entries sit in a category. */
  countFor: (categoryId: string) => number
  /** Adds the category, or returns a message explaining why it cannot. */
  onAdd: (name: string) => string | null
  onRemove: (category: Category) => void
}) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setError('Give the category a name, for example Breaking and Drilling.')
      return
    }
    const problem = onAdd(trimmed)
    if (problem) {
      setError(problem)
      return
    }
    setName('')
    setError('')
  }

  return (
    <>
      <ul className="mb-md flex flex-wrap gap-sm">
        {categories.map((category) => {
          const count = countFor(category.id)
          return (
            <li
              key={category.id}
              className="flex items-center gap-sm rounded border border-line bg-muted py-xs pl-md pr-xs"
            >
              <span className="text-sm text-ink">
                {category.name} <span className="tabular text-slate-soft">({count})</span>
              </span>
              <button
                type="button"
                disabled={count > 0}
                onClick={() => onRemove(category)}
                className="btn px-sm text-slate-soft hover:bg-surface hover:text-status-overdue"
              >
                <Trash2 className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="sr-only">
                  {count > 0
                    ? `${category.name} cannot be removed, it holds ${count} tools`
                    : `Remove the ${category.name} category`}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      <p className="mb-md text-sm text-slate-soft">
        A category can only be removed once it holds no tools. Move the tools to another category
        first.
      </p>
      <form onSubmit={submit} noValidate className="flex flex-wrap items-end gap-sm">
        <div className="min-w-[14rem] flex-1">
          <Field label="Add a category" htmlFor="new-category" error={error}>
            <input
              id="new-category"
              className="field-input"
              value={name}
              placeholder="Welding and Fabrication"
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'new-category-error' : undefined}
              onChange={(e) => { setName(e.target.value); setError('') }}
            />
          </Field>
        </div>
        <button type="submit" className="btn-secondary px-md">
          <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
          Add category
        </button>
      </form>
    </>
  )
}
