/**
 * Opening a staff account on SC-23, in a section of its own above the list.
 *
 * The form takes exactly the fields the route takes, the name, the work email,
 * the phone, the role and, for counter staff, the branch. It never shows or
 * asks for a password. Nothing is sent until the question below the fields has
 * been answered, and it says that the person chooses their own password from a
 * link sent to the address given.
 *
 * A refusal from the server comes back as a 422, and the form goes back to
 * the fields with each message under the field it names, listed above the form
 * as well with a link to each. A 409 or a 403 shows the server's sentence in
 * the question. One press of the answer sends one request, and it is disabled
 * while it is in flight. The body is written in staff-form.ts.
 */

import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { UserPlus, X } from 'lucide-react'
import { openStaffAccount } from '../../shared/api/admin-users'
import type { NewStaffAccountRequest, StaffAccountCreated } from '../../shared/api/contract'
import { otherFieldMessages } from '../../shared/api/problem-fields'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { FormProblems } from './SC21-Form-Problems'
import { WriteQuestion } from './SC20-Write-Question'
import { StaffFields } from './SC23-Staff-Fields'
import { EMPTY_STAFF_DRAFT, NEW_STAFF_FIELD_ORDER, newStaffRequestFrom, staffFieldId } from './staff-form'
import type { StaffDraft, StaffDraftErrors, StaffField } from './staff-form'
import { STAFF_ROLE_LABEL } from './staff-words'
import { useBranchList } from './use-branch-list'
import { useUserWrite } from './use-user-write'

const NO_ERRORS: FieldErrors = {}
const HEADING_ID = 'new-staff-heading'

/** Where focus goes next. A new object each time, so the same place twice still moves it. */
type FocusTarget = { to: 'problems' | 'submit' }

function Question({ body }: { body: NewStaffAccountRequest }) {
  const branches = useBranchList()
  const where = body.branchCode === null ? 'across every branch' : `at ${branches.nameOf(body.branchCode)}`
  return (
    <>
      <p>
        They will work as {STAFF_ROLE_LABEL[body.role].toLowerCase()} {where}.
      </p>
      <p>
        Nobody chooses a password for them here. A link goes to <span className="break-all">{body.email}</span>, and they
        choose their own password from it.
      </p>
    </>
  )
}

export function StaffCreate({
  onCreated,
  onClose,
}: {
  /** Called with what the server answered. */
  onCreated: (created: StaffAccountCreated) => void
  onClose: () => void
}) {
  const write = useUserWrite('staff_opened', 'new')
  const [draft, setDraft] = useState<StaffDraft>(EMPTY_STAFF_DRAFT)
  const [formErrors, setFormErrors] = useState<StaffDraftErrors>({})
  const [serverErrors, setServerErrors] = useState<FieldErrors>(NO_ERRORS)
  const [asking, setAsking] = useState<NewStaffAccountRequest | null>(null)
  const [focusTarget, setFocusTarget] = useState<FocusTarget | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const problemsRef = useRef<HTMLDivElement>(null)
  const submitRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  useEffect(() => {
    if (focusTarget === null) return
    if (focusTarget.to === 'problems') problemsRef.current?.focus()
    else submitRef.current?.focus()
  }, [focusTarget])

  const errorOf = (field: StaffField): string | undefined => serverErrors[field] ?? formErrors[field]
  const problems = NEW_STAFF_FIELD_ORDER.flatMap((field) => {
    const message = errorOf(field)
    return message ? [{ id: staffFieldId('new-staff', field), message }] : []
  })
  const leftOver = otherFieldMessages(serverErrors, NEW_STAFF_FIELD_ORDER)

  function change<Field extends StaffField>(field: Field, value: StaffDraft[Field]) {
    setDraft((current) => ({ ...current, [field]: value }))
    setFormErrors((current) => ({ ...current, [field]: undefined }))
    if (serverErrors[field] !== undefined) {
      setServerErrors((current) => Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)))
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    write.clearFailure()
    const checked = newStaffRequestFrom(draft)
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
    write.send(() => openStaffAccount(sent), {
      onAnswer: onCreated,
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
    <section aria-labelledby={HEADING_ID} className="card mb-lg min-w-0">
      <div className="border-b border-line px-lg py-md">
        <h3 id={HEADING_ID} ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-ink">
          A new staff account
        </h3>
      </div>
      <form noValidate onSubmit={submit} aria-label="The new staff account" className="p-lg">
        <FormProblems
          ref={problemsRef}
          problems={problems}
          leftOver={leftOver}
          detail={write.failure?.kind === 'refused' ? write.failure.detail : null}
        />
        <div className="grid gap-md sm:grid-cols-2">
          <StaffFields
            form="new-staff"
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
                <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
                Create the account
              </button>
              <button type="button" className="btn-secondary px-md" onClick={onClose}>
                <X className="h-4 w-4 shrink-0" aria-hidden="true" />
                Close the form
              </button>
            </div>
          ) : (
            <WriteQuestion
              id="new-staff-question"
              headingLevel={4}
              heading={`Create an account for ${asking.fullName === '' ? 'this person' : asking.fullName}?`}
              answer="Yes, create it"
              pendingAnswer="Creating the account"
              cancel="Go back to the form"
              refusedTitle="The account was not created"
              pending={write.pending}
              failure={write.failure}
              onAnswer={answer}
              onCancel={goBack}
            >
              <Question body={asking} />
            </WriteQuestion>
          )}
        </div>
      </form>
    </section>
  )
}
