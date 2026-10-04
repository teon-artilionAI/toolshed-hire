/**
 * The model form on SC-20 inside its own section, for a new model or one that
 * exists.
 *
 * A model that exists is read by its own route, `GET /api/admin/models/{id}`,
 * before its form opens, so the form starts from the model as the server holds
 * it and not from a row of the list. A model a write answered with is already
 * in the cache under its key. That read has the shared loading and failed
 * states, and a model the server does not know says so plainly. The form needs the
 * categories for its menu, so it waits for them too.
 *
 * The heading of the section takes focus when it opens, so a keyboard carries
 * on from the top of the form.
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AdminCategory, AdminModel } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { branchDateTime } from '../../shared/today'
import { EmptyState } from '../../shared/ui'
import { isNotFound } from '../counter/counter-refusal'
import { NEW_MODEL } from './catalogue-address'
import { ModelForm } from './SC20-Model-Form'

/** What the form needs from the screen. */
interface EditorProps {
  /** The categories for the menu, once they have been read. */
  categories: readonly AdminCategory[] | undefined
  /** The failure of the categories read, when it failed. */
  categoriesFailure: unknown
  retryCategories: () => void
  onSaved: (saved: AdminModel, movedAFigure: boolean) => void
  onClose: () => void
}

const HEADING_ID = 'model-editor-heading'

function Frame({ title, children }: { title: string; children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  return (
    <section aria-labelledby={HEADING_ID} className="card mb-lg min-w-0">
      <div className="border-b border-line px-lg py-md">
        <h2 id={HEADING_ID} ref={heading} tabIndex={-1} className="break-words text-lg font-semibold text-ink">
          {title}
        </h2>
      </div>
      <div className="p-lg">{children}</div>
    </section>
  )
}

function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button type="button" className="btn-secondary px-md" onClick={onClose}>
      <X className="h-4 w-4 shrink-0" aria-hidden="true" />
      Close the form
    </button>
  )
}

/** The form, once the categories for its menu are there. */
function WithCategories({ model, ...props }: EditorProps & { model: AdminModel | null }) {
  if (props.categories === undefined) {
    return props.categoriesFailure ? (
      <ErrorState what="the categories for the form" error={props.categoriesFailure} onRetry={props.retryCategories}>
        <CloseButton onClose={props.onClose} />
      </ErrorState>
    ) : (
      <LoadingState label="Loading the categories." shape="detail" count={1} />
    )
  }
  return (
    <ModelForm
      key={model?.id ?? NEW_MODEL}
      model={model}
      categories={props.categories}
      onSaved={props.onSaved}
      onClose={props.onClose}
    />
  )
}

function ExistingModel({ id, ...props }: EditorProps & { id: string }) {
  const read = useQuery(adminQueries.model(id))
  const phase = queryPhase(read)
  // Once the form is open it stays open, so a later read in the background
  // that fails never throws away what the owner has typed.
  if (read.data !== undefined) {
    return (
      <Frame title={`Change ${read.data.name}`}>
        <p className="mb-md text-sm text-slate-soft">Last changed {branchDateTime(read.data.updatedAt)}.</p>
        <WithCategories model={read.data} {...props} />
      </Frame>
    )
  }
  if (phase === 'failed' && isNotFound(read.error)) {
    return (
      <Frame title="That model is not in the catalogue">
        <EmptyState
          title="There is no model with that key"
          body="The address may be old or mistyped. Close the form and choose the model from the list."
          action={<CloseButton onClose={props.onClose} />}
        />
      </Frame>
    )
  }
  return (
    <Frame title="Opening the model">
      {phase === 'failed' ? (
        <ErrorState what="the model" error={read.error} onRetry={() => void read.refetch()}>
          <CloseButton onClose={props.onClose} />
        </ErrorState>
      ) : (
        <LoadingState label="Loading the model." shape="detail" count={1} />
      )}
    </Frame>
  )
}

export function ModelEditor({ editing, ...props }: EditorProps & { editing: string }) {
  if (editing === NEW_MODEL) {
    return (
      <Frame title="Add a model">
        <WithCategories model={null} {...props} />
      </Frame>
    )
  }
  return <ExistingModel key={editing} id={editing} {...props} />
}
