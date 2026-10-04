/**
 * The category form on SC-20, for adding a category or changing one.
 *
 * Adding sends every field the route takes, and changing sends only the
 * fields that differ from what the server holds. The parent is chosen from
 * the top level categories only, because nesting stops at two levels. Nothing
 * is sent until the question below the fields has been answered.
 *
 * A refusal from the server comes back as a 422, and the form goes back to
 * the fields with each message under the field it names, listed above the
 * form as well. A duplicate code or slug, and a parent the server will not
 * nest under, are refused that way. A 409 or a 403 shows the server's
 * sentence in the question. The rules and the bodies are in category-form.ts.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Plus, Save, X } from 'lucide-react'
import { changeCategory, createCategory } from '../../shared/api/admin-catalogue'
import type { AdminCategory, CategoryChangesRequest, NewCategoryRequest } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { Notice } from '../../shared/ui'
import { ProblemList, SelectInput, TextArea, TextInput } from '../counter/counter-fields'
import {
  CATEGORY_FIELD_ORDER,
  EMPTY_CATEGORY_DRAFT,
  TOP_LEVEL,
  categoryChangesFrom,
  draftOfCategory,
  newCategoryRequestFrom,
  parentChoices,
} from './category-form'
import type { CategoryDraft, CategoryDraftErrors, CategoryField } from './category-form'
import { WriteQuestion } from './SC20-Write-Question'
import { useCatalogueWrite } from './use-catalogue-write'

type Asking = { kind: 'add'; body: NewCategoryRequest } | { kind: 'change'; body: CategoryChangesRequest }

type FocusTarget = { to: 'problems' | 'submit' }

/** What the details are called in a sentence. */
const DETAIL_NOUN: Record<Exclude<CategoryField, 'parentCategoryId'>, string> = {
  name: 'the name',
  code: 'the code',
  slug: 'the name in the web address',
  sortOrder: 'the place in the list',
  description: 'the description',
}

const NO_ERRORS: FieldErrors = {}

function fieldId(field: CategoryField): string {
  return `category-${field}`
}

function nameOf(categories: readonly AdminCategory[], id: string | null | undefined): string {
  return categories.find((category) => category.id === id)?.name ?? 'another category'
}

/** The sentences of the question, from what is about to be sent. */
function consequence(asking: Asking, categories: readonly AdminCategory[]): string[] {
  if (asking.kind === 'add') {
    const place =
      asking.body.parentCategoryId === null
        ? 'It sits at the top level.'
        : `It sits under ${nameOf(categories, asking.body.parentCategoryId)}.`
    return [place, 'It starts switched on, in the catalogue customers browse.']
  }
  const sentences: string[] = []
  const nouns = (Object.keys(DETAIL_NOUN) as (keyof typeof DETAIL_NOUN)[])
    .filter((field) => asking.body[field] !== undefined)
    .map((field) => DETAIL_NOUN[field])
  if (nouns.length > 0) {
    const joined = nouns.length === 1 ? nouns[0] : `${nouns.slice(0, -1).join(', ')} and ${nouns.at(-1)}`
    sentences.push(`${joined.charAt(0).toUpperCase()}${joined.slice(1)} ${nouns.length === 1 ? 'changes' : 'change'}.`)
  }
  if (asking.body.parentCategoryId !== undefined) {
    sentences.push(
      asking.body.parentCategoryId === null
        ? 'It moves to the top level.'
        : `It moves under ${nameOf(categories, asking.body.parentCategoryId)}.`,
    )
  }
  return sentences
}

export function CategoryForm({
  category,
  categories,
  onSaved,
  onClose,
}: {
  /** The category to change, or null to add one. */
  category: AdminCategory | null
  categories: readonly AdminCategory[]
  onSaved: (saved: AdminCategory) => void
  onClose: () => void
}) {
  const write = useCatalogueWrite(category === null ? 'category_created' : 'category_changed', category?.id ?? 'new')
  const [draft, setDraft] = useState<CategoryDraft>(() =>
    category === null ? EMPTY_CATEGORY_DRAFT : draftOfCategory(category),
  )
  const [formErrors, setFormErrors] = useState<CategoryDraftErrors>({})
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_ERRORS)
  const [asking, setAsking] = useState<Asking | null>(null)
  const [unchanged, setUnchanged] = useState(false)
  const [focusTarget, setFocusTarget] = useState<FocusTarget | null>(null)
  const problemsRef = useRef<HTMLDivElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (focusTarget === null) return
    if (focusTarget.to === 'problems') problemsRef.current?.focus()
    else submitRef.current?.focus()
  }, [focusTarget])

  const errorOf = (field: CategoryField): string | undefined => serverErrors[field] ?? formErrors[field]
  const problems = CATEGORY_FIELD_ORDER.flatMap((field) => {
    const message = errorOf(field)
    return message ? [{ id: fieldId(field), message }] : []
  })
  const leftOver = otherFieldMessages(serverErrors, CATEGORY_FIELD_ORDER)
  const refusal = write.failure?.kind === 'refused' ? write.failure : null
  const fixCount = problems.length + leftOver.length
  const busy = asking !== null || write.pending

  function change(field: CategoryField, value: string) {
    setDraft((current) => ({ ...current, [field]: value }))
    setUnchanged(false)
    setFormErrors((current) => ({ ...current, [field]: undefined }))
    if (serverErrors[field] !== undefined) {
      setServerErrors((current) => Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)))
    }
  }

  function control(field: CategoryField) {
    return { id: fieldId(field), value: draft[field], onChange: (value: string) => change(field, value), error: errorOf(field), disabled: busy }
  }

  function holdBack(errors: CategoryDraftErrors) {
    setFormErrors(errors)
    setFocusTarget({ to: 'problems' })
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    write.clearFailure()
    if (category === null) {
      const checked = newCategoryRequestFrom(draft)
      if (checked.errors !== null) return holdBack(checked.errors)
      setFormErrors({})
      setAsking({ kind: 'add', body: checked.body })
      return
    }
    const checked = categoryChangesFrom(category, draft)
    if (checked.errors !== null) return holdBack(checked.errors)
    setFormErrors({})
    if (Object.keys(checked.body).length === 0) {
      setUnchanged(true)
      return
    }
    setAsking({ kind: 'change', body: checked.body })
  }

  function answer() {
    if (asking === null) return
    const outcome = {
      onAnswer: onSaved,
      onRefused: (fields: FieldErrors) => {
        setServerErrors(fields)
        setAsking(null)
        setFocusTarget({ to: 'problems' })
      },
    }
    if (asking.kind === 'add') {
      const body = asking.body
      write.send(() => createCategory(body), outcome)
    } else if (category !== null) {
      const body = asking.body
      write.send(() => changeCategory(category.id, body), outcome)
    }
  }

  const parents = parentChoices(categories, category?.id ?? null)
  const parentOptions = [
    { value: TOP_LEVEL, label: 'Nothing, it is a top level category' },
    ...parents.map((parent) => ({ value: parent.id, label: parent.isActive ? parent.name : `${parent.name} (switched off)` })),
  ]
  const name = draft.name.trim() === '' ? 'this category' : draft.name.trim()

  return (
    <form noValidate onSubmit={submit} aria-label={category === null ? 'The new category' : `The details of ${category.name}`}>
      {(fixCount > 0 || refusal !== null) && (
        <div ref={problemsRef} tabIndex={-1} className="mb-md">
          <Notice
            tone="error"
            title={
              fixCount === 0
                ? 'Nothing has been saved yet.'
                : `Nothing has been saved yet. ${fixCount} ${fixCount === 1 ? 'answer needs' : 'answers need'} fixing.`
            }
          >
            {fixCount === 0 && refusal !== null && <p>{refusal.detail}</p>}
            <ProblemList problems={problems} />
            {leftOver.length > 0 && (
              <ul className="mt-xs list-disc pl-lg">
                {leftOver.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </Notice>
        </div>
      )}
      {unchanged && (
        <div className="mb-md">
          <Notice tone="info" title="Nothing has changed yet">
            <p>Every field still holds what the catalogue holds, so there is nothing to save.</p>
          </Notice>
        </div>
      )}
      <div className="grid gap-md sm:grid-cols-2">
        <TextInput {...control('name')} label="Name" help="As customers see it." autoComplete="off" />
        <TextInput {...control('code')} label="Code" help="Short, as staff read it out, for example BREAK-DRILL." autoComplete="off" />
        <TextInput {...control('slug')} label="Name in the web address" help="For example breaking-drilling." autoComplete="off" />
        <SelectInput
          {...control('parentCategoryId')}
          label="Sits under"
          help="Only a top level category is offered, because categories go two levels deep and no deeper."
          options={parentOptions}
        />
        <TextInput
          {...control('sortOrder')}
          label="Place in the list"
          help="Lower numbers come first among the categories at the same level."
          inputMode="numeric"
          autoComplete="off"
        />
      </div>
      <div className="mt-md">
        <TextArea {...control('description')} label="Description" help="Optional. What the category holds." rows={2} />
      </div>
      <div className="mt-lg">
        {asking === null ? (
          <div className="flex flex-wrap gap-sm">
            <button ref={submitRef} type="submit" className="btn-primary px-md">
              {category === null ? (
                <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
              ) : (
                <Save className="h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              {category === null ? 'Add the category' : 'Save the changes'}
            </button>
            <button type="button" className="btn-secondary px-md" onClick={onClose}>
              <X className="h-4 w-4 shrink-0" aria-hidden="true" />
              Close the form
            </button>
          </div>
        ) : (
          <WriteQuestion
            id="category-save"
            heading={category === null ? `Add ${name} to the categories?` : `Save the changes to ${category.name}?`}
            answer={category === null ? 'Yes, add it' : 'Yes, save the changes'}
            pendingAnswer={category === null ? 'Adding it' : 'Saving the changes'}
            cancel="Go back to the form"
            refusedTitle={category === null ? 'The category was not added' : 'The changes were not saved'}
            pending={write.pending}
            failure={write.failure}
            onAnswer={answer}
            onCancel={() => {
              write.clearFailure()
              setAsking(null)
              setFocusTarget({ to: 'submit' })
            }}
          >
            {consequence(asking, categories).map((sentence) => (
              <p key={sentence}>{sentence}</p>
            ))}
          </WriteQuestion>
        )}
      </div>
    </form>
  )
}
