/**
 * A registration or account request that did not work, in front of the person.
 *
 * account-failure.ts sorts a failure into one of four answers and this draws
 * three of them. A wait says how long. A refusal shows the server's sentence,
 * and any message about a field the form has no input for. A fault is the
 * shared error state with a way to try again.
 *
 * A link that is no longer good is not drawn here. It ends what the screen was
 * doing, so each screen shows a state of its own for it.
 */

import { ErrorState } from '../../shared/async-states'
import { Notice } from '../../shared/ui'
import type { AccountFailure } from './account-failure'

export const TOO_MANY_ATTEMPTS_TITLE = 'Too many attempts'

export function AccountFailureNotice({
  failure,
  refusedTitle,
  faultHeading,
  fieldsAreShown = false,
  otherMessages = [],
  onRetry,
}: {
  failure: AccountFailure
  /** The heading over a refusal. */
  refusedTitle: string
  /** The whole heading when the request failed some other way. */
  faultHeading: string
  /** True when the form shows a message under at least one of its own fields.
   *  The server's summary is then left out, because the fields say it better. */
  fieldsAreShown?: boolean
  /** Messages about fields the form has no input for. */
  otherMessages?: readonly string[]
  onRetry: () => void
}) {
  if (failure.kind === 'linkInvalid') return null
  if (failure.kind === 'fault') {
    return <ErrorState heading={faultHeading} error={failure.error} onRetry={onRetry} />
  }
  if (failure.kind === 'wait') {
    return (
      <Notice tone="error" title={TOO_MANY_ATTEMPTS_TITLE}>
        <p>{failure.message}</p>
      </Notice>
    )
  }
  if (fieldsAreShown && otherMessages.length === 0) return null
  return (
    <Notice tone="error" title={refusedTitle}>
      {!fieldsAreShown && <p>{failure.detail}</p>}
      {otherMessages.length > 0 && (
        <ul className="mt-xs list-disc pl-lg">
          {otherMessages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </Notice>
  )
}
