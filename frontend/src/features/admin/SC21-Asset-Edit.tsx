/**
 * Changing the paperwork of a unit on SC-21, inside the unit.
 *
 * The serial number, the grade, the meter reading and the notes can change.
 * The tag, the model and the branch are shown read only above them, because
 * they never change once a unit is registered. Saving sends only the fields
 * that differ from what the server holds, and asks first, naming what changes.
 *
 * Each 422 goes under the field it names and is listed above the form with a
 * link to it. A 409 or a 403 shows the server's sentence in the question. One
 * press of the answer sends one request, disabled while it is in flight.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Save, X } from 'lucide-react'
import { changeAsset } from '../../shared/api/admin-assets'
import type { AdminAssetDetail, AssetChangesRequest } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { Notice } from '../../shared/ui'
import { ASSET_CHANGES_FIELD_ORDER, assetChangesFrom, assetFieldId, draftOfAsset } from './asset-form'
import type { AssetChangesDraft, AssetChangesField, AssetDraftErrors, NewAssetField } from './asset-form'
import { PaperworkFields } from './SC21-Asset-Fields'
import { FormProblems } from './SC21-Form-Problems'
import { WriteQuestion } from './SC20-Write-Question'
import { useAssetWrite } from './use-asset-write'

const NO_ERRORS: FieldErrors = {}

/** What each field is called in a sentence. */
const FIELD_NOUN: Record<AssetChangesField, string> = {
  serialNumber: 'the serial number',
  conditionGrade: 'the condition grade',
  hourMeterReading: 'the meter reading',
  notes: 'the notes',
}

/** "A changes", "A and B change", or "A, B and C change", with a capital letter. */
function whatChanges(changes: AssetChangesRequest): string {
  const nouns = ASSET_CHANGES_FIELD_ORDER.filter((field) => changes[field] !== undefined).map((field) => FIELD_NOUN[field])
  const joined = nouns.length <= 1 ? nouns.join('') : `${nouns.slice(0, -1).join(', ')} and ${nouns.at(-1)}`
  return `${joined.charAt(0).toUpperCase()}${joined.slice(1)} ${nouns.length === 1 ? 'changes' : 'change'}.`
}

/** Where focus goes next. A new object each time, so the same place twice still moves it. */
type FocusTarget = { to: 'problems' | 'submit' }

function FixedFacts({ unit }: { unit: AdminAssetDetail }) {
  return (
    <div className="mb-md rounded bg-muted p-md text-sm">
      <p className="text-ink">
        Tag <span className="break-all font-mono">{unit.assetTag}</span>, {unit.modelName}, at {unit.branchName}.
      </p>
      <p className="mt-xs text-slate-soft">The tag, the model and the branch never change once a unit is registered.</p>
    </div>
  )
}

export function AssetEdit({
  unit,
  onSaved,
  onClose,
}: {
  unit: AdminAssetDetail
  onSaved: (unit: AdminAssetDetail) => void
  onClose: () => void
}) {
  const write = useAssetWrite('unit_changed', unit.assetTag)
  const [draft, setDraft] = useState<AssetChangesDraft>(() => draftOfAsset(unit))
  const [formErrors, setFormErrors] = useState<AssetDraftErrors>({})
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_ERRORS)
  const [asking, setAsking] = useState<AssetChangesRequest | null>(null)
  const [unchanged, setUnchanged] = useState(false)
  const [focusTarget, setFocusTarget] = useState<FocusTarget | null>(null)
  const problemsRef = useRef<HTMLDivElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (focusTarget === null) return
    if (focusTarget.to === 'problems') problemsRef.current?.focus()
    else submitRef.current?.focus()
  }, [focusTarget])

  const errorOf = (field: NewAssetField): string | undefined => serverErrors[field] ?? formErrors[field]
  const problems = ASSET_CHANGES_FIELD_ORDER.flatMap((field) => {
    const message = errorOf(field)
    return message ? [{ id: assetFieldId(field), message }] : []
  })
  const leftOver = otherFieldMessages(serverErrors, ASSET_CHANGES_FIELD_ORDER)

  function change(field: AssetChangesField, value: string) {
    setDraft((current) => ({ ...current, [field]: value }))
    setUnchanged(false)
    setFormErrors((current) => ({ ...current, [field]: undefined }))
    if (serverErrors[field] !== undefined) {
      setServerErrors((current) => Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)))
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    write.clearFailure()
    const checked = assetChangesFrom(unit, draft)
    if (checked.errors !== null) {
      setFormErrors(checked.errors)
      setFocusTarget({ to: 'problems' })
      return
    }
    setFormErrors({})
    if (Object.keys(checked.body).length === 0) {
      setUnchanged(true)
      return
    }
    setAsking(checked.body)
  }

  function answer() {
    if (asking === null) return
    const sent = asking
    write.send(() => changeAsset(unit.assetTag, sent), {
      onAnswer: onSaved,
      onRefused: (fields) => {
        setServerErrors(fields)
        setAsking(null)
        setFocusTarget({ to: 'problems' })
      },
    })
  }

  function goBack() {
    write.clearFailure()
    setAsking(null)
    setFocusTarget({ to: 'submit' })
  }

  return (
    <form noValidate onSubmit={submit} aria-label={`The details of ${unit.assetTag}`}>
      <FormProblems
        ref={problemsRef}
        problems={problems}
        leftOver={leftOver}
        detail={write.failure?.kind === 'refused' ? write.failure.detail : null}
      />
      {unchanged && (
        <div className="mb-md">
          <Notice tone="info" title="Nothing has changed yet">
            <p>Every field still holds what the register holds, so there is nothing to save.</p>
          </Notice>
        </div>
      )}
      <FixedFacts unit={unit} />
      <div className="grid gap-md sm:grid-cols-2">
        <PaperworkFields
          draft={draft}
          onChange={change}
          control={{ errorOf, disabled: asking !== null || write.pending }}
        />
      </div>
      <div className="mt-lg">
        {asking === null ? (
          <div className="flex flex-wrap gap-sm">
            <button ref={submitRef} type="submit" className="btn-primary px-md">
              <Save className="h-4 w-4 shrink-0" aria-hidden="true" />
              Save the changes
            </button>
            <button type="button" className="btn-secondary px-md" onClick={onClose}>
              <X className="h-4 w-4 shrink-0" aria-hidden="true" />
              Keep the details as they are
            </button>
          </div>
        ) : (
          <WriteQuestion
            id="asset-change"
            headingLevel={4}
            heading={`Save the changes to ${unit.assetTag}?`}
            answer="Yes, save the changes"
            pendingAnswer="Saving the changes"
            cancel="Go back to the form"
            refusedTitle="The changes were not saved"
            pending={write.pending}
            failure={write.failure}
            onAnswer={answer}
            onCancel={goBack}
          >
            <p>{whatChanges(asking)}</p>
            <p>The change is kept in the history of the unit and in the audit trail.</p>
          </WriteQuestion>
        )}
      </div>
    </form>
  )
}
