/**
 * The password reset state of SC-06.
 *
 * Asking for a reset link and choosing a new password are a later change. The
 * API has no route for either yet. Until it does, this state says so in plain
 * words and does nothing else. It takes no email address and shows no
 * confirmation, because a form that reported a link as sent when none was
 * would leave a person waiting for an email that is never coming.
 */

import { Card, Notice } from '../../shared/ui'

export const RESET_UNAVAILABLE_TITLE = 'Password reset is not available yet'

export function PasswordResetUnavailable({ onBackToSignIn }: { onBackToSignIn: () => void }) {
  return (
    <Card title="Reset your password">
      <Notice tone="warn" title={RESET_UNAVAILABLE_TITLE}>
        <p>
          This screen cannot send a reset link or change a password yet. Nothing has been sent and
          your password has not changed.
        </p>
      </Notice>
      <button type="button" className="btn-primary mt-lg px-lg" onClick={onBackToSignIn}>
        Back to sign in
      </button>
    </Card>
  )
}
