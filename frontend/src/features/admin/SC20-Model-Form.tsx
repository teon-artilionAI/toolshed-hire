/**
 * The model form on SC-20, for adding a model or changing one.
 *
 * Adding sends every field the route takes. Changing sends only the fields
 * that differ from what the server holds, and never the stock code, which is
 * shown read only. Nothing is sent until the question below the fields has
 * been answered, and it says in words what is about to happen. When a figure
 * moves, it says that bookings already made keep the rate they were booked at.
 *
 * The browser holds no copy of the rules about money. A refusal from the
 * server comes back as a 422, and the form goes back to the fields with each
 * message under the field it names, listed above the form as well with a link
 * to each, and any message about a field the form has no box for listed with
 * them. A 409 or a 403 shows the server's sentence in the question. One press
 * of the answer sends one request, and it is disabled while it is in flight.
 * The rules and the bodies are in model-form.ts.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Plus, Save, X } from 'lucide-react'
import { changeModel, createModel } from '../../shared/api/admin-catalogue'
import { rememberAdminModel } from '../../shared/api/admin-queries'
import type { AdminCategory, AdminModel, ModelChangesRequest, NewModelRequest } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { Notice } from '../../shared/ui'
import { ProblemList } from '../counter/counter-fields'
import { NEW_MODEL } from './catalogue-address'
import {
  EMPTY_MODEL_DRAFT,
  MODEL_FIELD_ORDER,
  draftOfModel,
  modelChangesFrom,
  modelFieldId,
  movesAFigure,
  newModelRequestFrom,
} from './model-form'
import type { ModelDraft, ModelDraftErrors, ModelField } from './model-form'
import { ModelFields } from './SC20-Model-Fields'
import { AddModelQuestion, ChangeModelQuestion } from './SC20-Model-Save-Question'
import { useCatalogueWrite } from './use-catalogue-write'

/** What the question is about to send. */
type Asking = { kind: 'add'; body: NewModelRequest } | { kind: 'change'; body: ModelChangesRequest }

/** Where focus goes next. A new object each time, so the same place twice still moves it. */
type FocusTarget = { to: 'problems' | 'submit' }

const NO_ERRORS: FieldErrors = {}

export function ModelForm({
  model,
  categories,
  onSaved,
  onClose,
}: {
  /** The model to change, or null to add one. */
  model: AdminModel | null
  categories: readonly AdminCategory[]
  /** Called with the model the server answered with, and whether a figure moved. */
  onSaved: (saved: AdminModel, movedAFigure: boolean) => void
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const write = useCatalogueWrite(model === null ? 'model_created' : 'model_changed', model?.id ?? NEW_MODEL)
  const [draft, setDraft] = useState<ModelDraft>(() => (model === null ? EMPTY_MODEL_DRAFT : draftOfModel(model)))
  const [formErrors, setFormErrors] = useState<ModelDraftErrors>({})
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

  const shownFields = MODEL_FIELD_ORDER.filter((field) => field !== 'sku' || model === null)
  const errorOf = (field: ModelField): string | undefined => serverErrors[field] ?? formErrors[field]
  const problems = shownFields.flatMap((field) => {
    const message = errorOf(field)
    return message ? [{ id: modelFieldId(field), message }] : []
  })
  const leftOver = otherFieldMessages(serverErrors, shownFields)
  const refusal = write.failure?.kind === 'refused' ? write.failure : null
  const somethingToFix = problems.length + leftOver.length > 0 || refusal !== null

  function change(field: ModelField, value: string) {
    setDraft((current) => ({ ...current, [field]: value }))
    setUnchanged(false)
    setFormErrors((current) => ({ ...current, [field]: undefined }))
    if (serverErrors[field] !== undefined) {
      setServerErrors((current) => Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)))
    }
  }

  function holdBack(errors: ModelDraftErrors) {
    setFormErrors(errors)
    setFocusTarget({ to: 'problems' })
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    write.clearFailure()
    if (model === null) {
      const checked = newModelRequestFrom(draft)
      if (checked.errors !== null) return holdBack(checked.errors)
      setFormErrors({})
      setAsking({ kind: 'add', body: checked.body })
      return
    }
    const checked = modelChangesFrom(model, draft)
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
      onRefused: (fields: FieldErrors) => {
        setServerErrors(fields)
        setAsking(null)
        setFocusTarget({ to: 'problems' })
      },
    }
    const saved = (answered: AdminModel) => {
      rememberAdminModel(queryClient, answered)
      onSaved(answered, asking.kind === 'change' && movesAFigure(asking.body))
    }
    if (asking.kind === 'add') {
      const body = asking.body
      write.send(() => createModel(body), { ...outcome, onAnswer: saved })
    } else if (model !== null) {
      const body = asking.body
      write.send(() => changeModel(model.id, body), { ...outcome, onAnswer: saved })
    }
  }

  function goBack() {
    write.clearFailure()
    setAsking(null)
    setFocusTarget({ to: 'submit' })
  }

  const question = { pending: write.pending, failure: write.failure, onAnswer: answer, onCancel: goBack }
  const fixCount = problems.length + leftOver.length

  return (
    <form noValidate onSubmit={submit} aria-label={model === null ? 'The new model' : `The details of ${model.name}`}>
      {somethingToFix && (
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

      <ModelFields
        draft={draft}
        sku={model?.sku ?? null}
        categories={categories}
        errorOf={errorOf}
        onChange={change}
        disabled={asking !== null || write.pending}
      />

      <div className="mt-lg">
        {asking === null ? (
          <div className="flex flex-wrap gap-sm">
            <button ref={submitRef} type="submit" className="btn-primary px-md">
              {model === null ? (
                <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
              ) : (
                <Save className="h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              {model === null ? 'Add the model' : 'Save the changes'}
            </button>
            <button type="button" className="btn-secondary px-md" onClick={onClose}>
              <X className="h-4 w-4 shrink-0" aria-hidden="true" />
              Close the form
            </button>
          </div>
        ) : asking.kind === 'add' ? (
          <AddModelQuestion body={asking.body} {...question} />
        ) : (
          model !== null && <ChangeModelQuestion model={model} changes={asking.body} {...question} />
        )}
      </div>
    </form>
  )
}
