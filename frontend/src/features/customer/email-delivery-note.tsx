/**
 * What to say when a link was sent to an address this system cannot reach.
 *
 * The API says `emailDeliverable` is false when this environment only delivers
 * email to one address and the one in question is not it. The screen must not
 * leave a person waiting for an email that is never coming, so it says so in
 * plain words and says what they can do in the meantime.
 *
 * The flag depends on the address and the configuration alone. It says nothing
 * about whether the address has an account, so showing this gives nothing away.
 */

import type { ReactNode } from 'react'
import { Notice } from '../../shared/ui'

export const DEMONSTRATION_EMAIL_TITLE = 'The link cannot reach this address'

export const DEMONSTRATION_EMAIL_REASON =
  'This demonstration only delivers email to one address, and this is not it, so the link cannot reach you.'

/** What an account can still do while its email address is unconfirmed. */
export const WITHOUT_THE_LINK =
  'You can still sign in, browse and hold equipment. A counter assistant can confirm a booking for you at a branch.'

/** @param children What the person can do instead, as a sentence or two. */
export function DemonstrationEmailNote({ children }: { children?: ReactNode }) {
  return (
    <Notice tone="warn" title={DEMONSTRATION_EMAIL_TITLE}>
      <p>{DEMONSTRATION_EMAIL_REASON}</p>
      {children && <p className="mt-xs">{children}</p>}
    </Notice>
  )
}
