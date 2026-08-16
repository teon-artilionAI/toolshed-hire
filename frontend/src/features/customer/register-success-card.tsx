/**
 * What SC-05 shows once the account exists.
 *
 * Confirmation screens that only say "success" waste the one moment the
 * customer is definitely paying attention. This one uses it to say what to
 * bring to the counter, because turning up without the right document is
 * the single most common reason a collection fails.
 */

import { Link } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import { Card } from '../../shared/ui'
import { ID_DOC_LABEL } from './customer-labels'
import type { RegistrationForm } from './register-form'

export function RegisterSuccessCard({ form }: { form: RegistrationForm }) {
  const firstName = form.fullName.trim().split(/\s+/)[0]
  const branch = branches.find((candidate) => candidate.code === form.homeBranch)

  return (
    <Card>
      <div className="flex items-start gap-md">
        <CheckCircle2
          className="mt-xs h-6 w-6 shrink-0 text-status-available"
          aria-hidden="true"
        />
        <div>
          <h2 className="text-lg font-semibold text-ink">
            Welcome to Toolshed Hire, {firstName}
          </h2>
          <p className="mt-sm text-sm text-slate-soft">
            Bring the {ID_DOC_LABEL[form.idDocType].toLowerCase()} you
            registered with when you collect. The counter checks it against the
            booking before any equipment leaves the branch.
          </p>
          <p className="mt-sm text-sm text-slate-soft">
            Your usual collection branch is set to {branch?.name}. You can
            choose a different branch on any booking.
          </p>
          <div className="mt-lg flex flex-wrap gap-sm">
            <Link to="/" className="btn-primary px-md">
              Start browsing equipment
            </Link>
            <Link to="/signin" className="btn-secondary px-md">
              Go to sign in
            </Link>
          </div>
        </div>
      </div>
    </Card>
  )
}
