/**
 * The three cards of the registration form on SC-05.
 *
 * Who the person is, how the counter will know them and where to bill, and
 * the password with the privacy notice. They only draw. What was typed, what
 * is wrong with it and what happens on submit all belong to
 * SC05-Register-Form.tsx, which hands each card the wiring for its fields.
 *
 * The identity card asks for the last four characters of the document and
 * says that the counter checks the full document at collection. The branches
 * in its menu are the ones the API lists. Until they arrive there is nothing
 * to choose from, and if they cannot be loaded the card says so in the place
 * of the menu.
 */

import { Link } from 'react-router-dom'
import {
  ID_DOCUMENT_LAST_LENGTH,
  ID_DOCUMENT_TYPES,
  MIN_PASSWORD_LENGTH,
} from '../../shared/api/account'
import type { Branch } from '../../shared/api/contract'
import type { QueryPhase } from '../../shared/api/query-phase'
import { ErrorState } from '../../shared/async-states'
import { PRIVACY_PATH } from '../../shared/navigation'
import { Card } from '../../shared/ui'
import { CheckboxField, PasswordField, SelectField, TextField } from './customer-fields'
import { ID_DOC_LABEL } from './customer-labels'
import type { TextFieldName } from './register-form'

/** What one text box or menu of the form is wired with. */
export interface FieldWiring {
  id: string
  value: string
  onChange: (value: string) => void
  onBlur: () => void
  error: string | undefined
}

/** Hands a card the wiring of one of its fields. */
export type WiringFor = (field: TextFieldName) => FieldWiring

/** The branch list as the form has it at this moment. */
export interface BranchChoices {
  phase: QueryPhase
  branches: readonly Branch[]
  /** What the read threw, when it failed. */
  error: unknown
  onRetry: () => void
}

const BRANCH_FIELD: TextFieldName = 'homeBranchCode'

export function YourDetailsCard({ control }: { control: WiringFor }) {
  return (
    <Card title="Your details">
      <div className="flex flex-col gap-md">
        <TextField
          {...control('fullName')}
          label="Full name"
          autoComplete="name"
          help="As it appears on your identity document."
          required
        />
        <TextField
          {...control('email')}
          label="Email address"
          type="email"
          inputMode="email"
          autoComplete="email"
          help="Booking confirmations and return reminders go here."
          required
        />
        <TextField
          {...control('phone')}
          label="Mobile number"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="082 441 7719"
          required
        />
      </div>
    </Card>
  )
}

function BranchMenu({ control, choices }: { control: WiringFor; choices: BranchChoices }) {
  if (choices.phase === 'failed') {
    return (
      <div id={BRANCH_FIELD}>
        <ErrorState
          what="the branches to choose from"
          error={choices.error}
          onRetry={choices.onRetry}
        />
      </div>
    )
  }
  const ready = choices.phase === 'ready'
  return (
    <SelectField
      {...control(BRANCH_FIELD)}
      label="Usual collection branch"
      help="You can choose a different branch on any booking."
      disabled={!ready}
      options={
        ready
          ? choices.branches.map((branch) => ({
              value: branch.code,
              label: `${branch.name}, ${branch.suburb}`,
            }))
          : [{ value: '', label: 'Loading the branches' }]
      }
    />
  )
}

export function IdentificationCard({
  control,
  choices,
}: {
  control: WiringFor
  choices: BranchChoices
}) {
  return (
    <Card title="Identification and billing">
      <div className="flex flex-col gap-md">
        <SelectField
          {...control('idDocumentType')}
          label="Identity document"
          options={ID_DOCUMENT_TYPES.map((type) => ({ value: type, label: ID_DOC_LABEL[type] }))}
        />
        <TextField
          {...control('idDocumentLast4')}
          label="Last four characters of the document number"
          autoComplete="off"
          maxLength={ID_DOCUMENT_LAST_LENGTH}
          help="Only the last four. Never type the whole number here. The counter checks the full document at collection."
          required
        />
        <TextField
          {...control('billingAddressLine1')}
          label="Billing address, first line"
          autoComplete="address-line1"
          help="The street address or the post box."
          required
        />
        <div className="grid gap-md sm:grid-cols-2">
          <TextField
            {...control('billingSuburb')}
            label="Billing suburb"
            autoComplete="address-level2"
            required
          />
          <TextField
            {...control('billingCity')}
            label="Billing city"
            autoComplete="address-level1"
            required
          />
        </div>
        <div className="max-w-[12rem]">
          <TextField
            {...control('billingPostalCode')}
            label="Postal code"
            inputMode="numeric"
            autoComplete="postal-code"
            required
          />
        </div>
        <div aria-busy={choices.phase === 'loading'}>
          <BranchMenu control={control} choices={choices} />
        </div>
      </div>
    </Card>
  )
}

export function PasswordAndPrivacyCard({
  control,
  accepted,
  onAccept,
  acceptError,
}: {
  control: WiringFor
  /** Whether the privacy notice has been accepted. */
  accepted: boolean
  onAccept: (accepted: boolean) => void
  acceptError: string | undefined
}) {
  return (
    <Card title="Password and privacy">
      <div className="flex flex-col gap-md">
        <PasswordField
          {...control('password')}
          label="Password"
          autoComplete="new-password"
          help={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        />
        <PasswordField
          {...control('confirmPassword')}
          label="Confirm password"
          autoComplete="new-password"
        />
        <div>
          <CheckboxField
            id="acceptsPrivacyNotice"
            checked={accepted}
            onChange={onAccept}
            error={acceptError}
          >
            I have read the privacy notice and I accept it.
          </CheckboxField>
          {/* It opens in a new tab, so what has been typed is still here. */}
          <Link
            to={PRIVACY_PATH}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-[2.75rem] cursor-pointer items-center text-sm font-medium
                       text-ink underline transition-colors duration-200 hover:text-slate"
          >
            Read the privacy notice (opens in a new tab)
          </Link>
        </div>
        <p className="text-sm text-slate-soft">
          A refundable deposit is taken at collection, and a late return is charged for each day.
        </p>
      </div>
    </Card>
  )
}
