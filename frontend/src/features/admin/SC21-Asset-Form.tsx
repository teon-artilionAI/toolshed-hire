/**
 * Registering a unit on SC-21, in a section of its own above the register.
 *
 * The form takes exactly the fields the route takes. The tag as it is painted
 * on the unit, the model, found by searching for it, the branch it belongs to,
 * and its paperwork. Nothing is sent until the question below the fields has
 * been answered, and it says that the unit starts at intake, where nobody can
 * book it, and that its tag, model and branch never change once it is
 * registered.
 *
 * A refusal from the server comes back as a 422, and the form goes back to
 * the fields with each message under the field it names, listed above the
 * form as well with a link to each, and any message about a field the form
 * has no box for listed with them. A cost the server could not read as an
 * amount gets a plain sentence in place of the server's. A 409 or a 403 shows
 * the server's sentence in the question. One press of the answer sends one
 * request, and it is disabled while it is in flight. The rules and the body
 * are in asset-form.ts.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { registerAsset } from '../../shared/api/admin-assets'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import type { AdminAssetDetail, NewAssetRequest } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { SelectInput, TextInput } from '../counter/counter-fields'
import { EMPTY_NEW_ASSET_DRAFT, NEW_ASSET_FIELD_ORDER, assetFieldId, newAssetRequestFrom, plainCostMessage } from './asset-form'
import type { AssetDraftErrors, NewAssetDraft, NewAssetField } from './asset-form'
import { DayInput, PaperworkFields } from './SC21-Asset-Fields'
import { FormProblems } from './SC21-Form-Problems'
import { ModelPicker } from './SC21-Model-Picker'
import { WriteQuestion } from './SC20-Write-Question'
import { useAssetWrite } from './use-asset-write'

const NO_ERRORS: FieldErrors = {}

/** Where focus goes next. A new object each time, so the same place twice still moves it. */
type FocusTarget = { to: 'problems' | 'submit' }

export function AssetRegistration({
  onRegistered,
  onClose,
}: {
  /** Called with the unit the server answered with. */
  onRegistered: (unit: AdminAssetDetail) => void
  onClose: () => void
}) {
  const write = useAssetWrite('unit_registered', 'new')
  const branches = useQuery(catalogueQueries.branches())
  const [draft, setDraft] = useState<NewAssetDraft>(EMPTY_NEW_ASSET_DRAFT)
  const [modelName, setModelName] = useState('')
  const [formErrors, setFormErrors] = useState<AssetDraftErrors>({})
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_ERRORS)
  const [asking, setAsking] = useState<NewAssetRequest | null>(null)
  const [focusTarget, setFocusTarget] = useState<FocusTarget | null>(null)
  const problemsRef = useRef<HTMLDivElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (focusTarget === null) return
    if (focusTarget.to === 'problems') problemsRef.current?.focus()
    else submitRef.current?.focus()
  }, [focusTarget])

  const errorOf = (field: NewAssetField): string | undefined => serverErrors[field] ?? formErrors[field]
  const problems = NEW_ASSET_FIELD_ORDER.flatMap((field) => {
    const message = errorOf(field)
    return message ? [{ id: assetFieldId(field), message }] : []
  })
  const leftOver = otherFieldMessages(serverErrors, NEW_ASSET_FIELD_ORDER)
  const branchList = branches.data?.items ?? []
  const branchName = branchList.find((branch) => branch.code === draft.branchCode)?.name ?? draft.branchCode
  const busy = asking !== null || write.pending

  function change(field: NewAssetField, value: string) {
    setDraft((current) => ({ ...current, [field]: value }))
    setFormErrors((current) => ({ ...current, [field]: undefined }))
    if (serverErrors[field] !== undefined) {
      setServerErrors((current) => Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)))
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    write.clearFailure()
    const checked = newAssetRequestFrom(draft)
    if (checked.errors !== null) {
      setFormErrors(checked.errors)
      setFocusTarget({ to: 'problems' })
      return
    }
    setFormErrors({})
    setAsking(checked.body)
  }

  function answer() {
    if (asking === null) return
    const sent = asking
    write.send(() => registerAsset(sent), {
      onAnswer: onRegistered,
      onRefused: (fields) => {
        setServerErrors(plainCostMessage(fields, sent))
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

  const branchOptions = [
    { value: '', label: 'Choose a branch' },
    ...branchList.map((branch) => ({ value: branch.code, label: branch.name })),
  ]

  return (
    <form noValidate onSubmit={submit} aria-label="The new unit">
      <FormProblems
        ref={problemsRef}
        problems={problems}
        leftOver={leftOver}
        detail={write.failure?.kind === 'refused' ? write.failure.detail : null}
      />
      <div className="grid gap-md sm:grid-cols-2">
        <TextInput
          id={assetFieldId('assetTag')}
          label="Asset tag"
          help="Capital letters and digits, as painted on the unit, for example TSH-DR-0042. It never changes once the unit is registered."
          value={draft.assetTag}
          onChange={(value) => change('assetTag', value)}
          error={errorOf('assetTag')}
          disabled={busy}
          autoComplete="off"
        />
        <SelectInput
          id={assetFieldId('branchCode')}
          label="Branch it belongs to"
          value={draft.branchCode}
          onChange={(value) => change('branchCode', value)}
          options={branchOptions}
          error={errorOf('branchCode')}
          help={branches.isError ? 'The branches could not be read. Close the form and open it again.' : undefined}
          disabled={busy}
        />
        <div className="sm:col-span-2">
          <ModelPicker
            id={assetFieldId('modelId')}
            legend="Which model it is"
            searchLabel="Find the model by name or stock code"
            selectLabel="Model"
            noChoice="Choose a model"
            chosenId={draft.modelId}
            onChoose={(model) => {
              change('modelId', model?.id ?? '')
              setModelName(model?.name ?? '')
            }}
            error={errorOf('modelId')}
            disabled={busy}
          />
        </div>
        <DayInput
          id={assetFieldId('acquiredOn')}
          label="Bought on"
          value={draft.acquiredOn}
          onChange={(value) => change('acquiredOn', value)}
          error={errorOf('acquiredOn')}
          disabled={busy}
        />
        <TextInput
          id={assetFieldId('acquisitionCost')}
          label="Cost, in rand"
          help="What the business paid for it, excluding VAT."
          value={draft.acquisitionCost}
          onChange={(value) => change('acquisitionCost', value)}
          error={errorOf('acquisitionCost')}
          disabled={busy}
          inputMode="decimal"
          autoComplete="off"
        />
        <PaperworkFields draft={draft} onChange={change} control={{ errorOf, disabled: busy }} />
      </div>

      <div className="mt-lg">
        {asking === null ? (
          <div className="flex flex-wrap gap-sm">
            <button ref={submitRef} type="submit" className="btn-primary px-md">
              <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
              Register the unit
            </button>
            <button type="button" className="btn-secondary px-md" onClick={onClose}>
              <X className="h-4 w-4 shrink-0" aria-hidden="true" />
              Close the form
            </button>
          </div>
        ) : (
          <WriteQuestion
            id="asset-register"
            heading={`Register ${asking.assetTag === '' ? 'this unit' : asking.assetTag}?`}
            answer="Yes, register it"
            pendingAnswer="Registering it"
            cancel="Go back to the form"
            refusedTitle="The unit was not registered"
            pending={write.pending}
            failure={write.failure}
            onAnswer={answer}
            onCancel={goBack}
          >
            <p>
              It starts at intake, so nobody can book it until it has been checked and commissioned.
            </p>
            <p>
              Its tag, its model and its branch never change once it is registered, so check them now. They are{' '}
              {asking.assetTag === '' ? 'no tag yet' : asking.assetTag}, {modelName === '' ? 'the model chosen' : modelName}{' '}
              and {branchName}.
            </p>
          </WriteQuestion>
        )}
      </div>
    </form>
  )
}
