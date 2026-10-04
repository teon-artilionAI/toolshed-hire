/**
 * Changing a staff account on SC-23, inside the account.
 *
 * The name, the phone, the role and the branch can change. The address the
 * person signs in with is shown read only, because an account keeps it.
 * Saving sends only the fields that differ from what the server holds, and
 * asks first, saying in words what changes.
 *
 * Moving the last active administrator to another role is refused by the
 * server with a 409, and the question shows its sentence, as it does a 403.
 * Each 422 goes under the field it names and is listed above the form with a
 * link to it. One press of the answer sends one request, disabled while it is
 * in flight.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Save, X } from 'lucide-react'
import { changeStaffAccount } from '../../shared/api/admin-users'
import type { AdminUser, StaffAccountChangesRequest } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { Notice } from '../../shared/ui'
import { FormProblems } from './SC21-Form-Problems'
import { WriteQuestion } from './SC20-Write-Question'
import { StaffFields } from './SC23-Staff-Fields'
import { STAFF_CHANGES_FIELD_ORDER, draftOfAccount, staffChangesFrom, staffFieldId } from './staff-form'
import type { StaffDraft, StaffDraftErrors, StaffField } from './staff-form'
import { STAFF_ROLE_LABEL } from './staff-words'
import { useBranchList } from './use-branch-list'
import { useUserWrite } from './use-user-write'

const NO_ERRORS: FieldErrors = {}

/** Where focus goes next. A new object each time, so the same place twice still moves it. */
type FocusTarget = { to: 'problems' | 'submit' }

/** Each change in a sentence of its own, in the order of the form. */
function changeSentences(changes: StaffAccountChangesRequest, branchName: (code: string) => string): string[] {
  const sentences: string[] = []
  if (changes.fullName !== undefined) sentences.push(`The name changes to ${changes.fullName}.`)
  if (changes.phone !== undefined) {
    sentences.push(changes.phone === null ? 'The phone number is taken off.' : `The phone number changes to ${changes.phone}.`)
  }
  if (changes.role === 'ADMIN') {
    sentences.push(`The role changes to ${STAFF_ROLE_LABEL.ADMIN.toLowerCase()}, with every branch, the reports, pricing and this screen.`)
  } else if (changes.role !== undefined) {
    sentences.push(`The role changes to ${STAFF_ROLE_LABEL[changes.role].toLowerCase()}.`)
  }
  if (changes.branchCode !== undefined && changes.branchCode !== null) {
    sentences.push(`They work at ${branchName(changes.branchCode)} from now.`)
  }
  return sentences
}

export function StaffEdit({
  user,
  onSaved,
  onClose,
}: {
  user: AdminUser
  onSaved: (user: AdminUser) => void
  onClose: () => void
}) {
  const write = useUserWrite('staff_changed', user.id)
  const branches = useBranchList()
  const [draft, setDraft] = useState<StaffDraft>(() => draftOfAccount(user))
  const [formErrors, setFormErrors] = useState<StaffDraftErrors>({})
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_ERRORS)
  const [asking, setAsking] = useState<StaffAccountChangesRequest | null>(null)
  const [unchanged, setUnchanged] = useState(false)
  const [focusTarget, setFocusTarget] = useState<FocusTarget | null>(null)
  const problemsRef = useRef<HTMLDivElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (focusTarget === null) return
    if (focusTarget.to === 'problems') problemsRef.current?.focus()
    else submitRef.current?.focus()
  }, [focusTarget])

  const errorOf = (field: StaffField): string | undefined => serverErrors[field] ?? formErrors[field]
  const problems = STAFF_CHANGES_FIELD_ORDER.flatMap((field) => {
    const message = errorOf(field)
    return message ? [{ id: staffFieldId('edit-staff', field), message }] : []
  })
  const leftOver = otherFieldMessages(serverErrors, STAFF_CHANGES_FIELD_ORDER)

  function change<Field extends StaffField>(field: Field, value: StaffDraft[Field]) {
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
    const checked = staffChangesFrom(user, draft)
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
    write.send(() => changeStaffAccount(user.id, sent), {
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
    <form noValidate onSubmit={submit} aria-label={`The details of ${user.fullName}`}>
      <FormProblems
        ref={problemsRef}
        problems={problems}
        leftOver={leftOver}
        detail={write.failure?.kind === 'refused' ? write.failure.detail : null}
      />
      {unchanged && (
        <div className="mb-md">
          <Notice tone="info" title="Nothing has changed yet">
            <p>Every field still holds what the account holds, so there is nothing to save.</p>
          </Notice>
        </div>
      )}
      <div className="mb-md rounded bg-muted p-md text-sm">
        <p className="break-all text-ink">Signs in as {user.email}</p>
        <p className="mt-xs text-slate-soft">An account keeps the address it was opened with.</p>
      </div>
      <div className="grid gap-md sm:grid-cols-2">
        <StaffFields
          form="edit-staff"
          draft={draft}
          onChange={change}
          errorOf={errorOf}
          disabled={asking !== null || write.pending}
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
              Keep the account as it is
            </button>
          </div>
        ) : (
          <WriteQuestion
            id="staff-change"
            headingLevel={4}
            heading={`Save the changes to the account of ${user.fullName}?`}
            answer="Yes, save the changes"
            pendingAnswer="Saving the changes"
            cancel="Go back to the form"
            refusedTitle="The changes were not saved"
            pending={write.pending}
            failure={write.failure}
            onAnswer={answer}
            onCancel={goBack}
          >
            {changeSentences(asking, branches.nameOf).map((sentence) => (
              <p key={sentence}>{sentence}</p>
            ))}
            <p>The audit trail keeps the change.</p>
          </WriteQuestion>
        )}
      </div>
    </form>
  )
}
