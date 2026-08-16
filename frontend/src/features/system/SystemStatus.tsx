/**
 * DEV-01 System Connectivity.
 *
 * WHY THIS SCREEN EXISTS
 * ======================
 * Four of the five load bearing decisions in this build were proved against
 * real infrastructure. The fifth was not: the React client had never called the
 * API at all. Every screen read from fixtures, there was no fetch anywhere in
 * the source, and the dev server had no proxy. So the claim that the browser
 * sees a single origin, with `/api/*` rewritten to Cloud Run server side and a
 * refresh cookie that can honestly be `SameSite=Strict`, was an assertion in a
 * document rather than something that had ever happened. That is precisely the
 * kind of decision that works locally and fails in production, or the reverse.
 *
 * This screen closes that gap and nothing more. It calls the real health
 * endpoint, signs in against the real sign in endpoint with a seeded account,
 * calls the protected `/api/me` with the token it was given, and then shows the
 * origin the browser actually used next to the path it actually requested, so a
 * reader can see for themselves that they are the same origin.
 *
 * IT IS NOT ONE OF THE TWENTY FOUR
 * ================================
 * SC-01 to SC-24 reconcile one to one with the documented screen inventory and
 * are untouched. This screen is DEV-01, deliberately outside that series, and
 * it is excluded from the screenshot capture that feeds the Task 1 appendix.
 * The twenty four still read from fixtures. Wiring them to the API is separate
 * work with its own budget, and doing it here would spend that budget early.
 *
 * The API being absent is the normal state during document work, so every call
 * here fails into an explanation rather than a blank page.
 */

import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Card, Notice, PageHeader, StatusPill } from '../../shared/ui'
import { PasswordField, TextField } from '../customer/customer-fields'
import {
  apiPath,
  asApiError,
  getCurrentUser,
  getHealth,
  resolvedApiUrl,
  signIn,
} from '../../shared/api'
import type { ApiUserAccount, HealthReport, SignInResult } from '../../shared/api'
import {
  DevelopmentScreenBanner,
  FactRow,
  FailureNotice,
  LiteralRow,
} from './system-panels'
import type { Loadable } from './system-panels'

/** The account seeded by backend/seed.py, and the password that script uses
 *  when SEED_PASSWORD is unset in development. Both are development values and
 *  neither exists in any deployed environment. */
const SEEDED_EMAIL = 'w.adonis@buildright.co.za'
const SEEDED_PASSWORD = 'toolshed-dev-password'

const HEALTH_ENDPOINT = '/health'
const SIGN_IN_ENDPOINT = '/auth/sign-in'
const ME_ENDPOINT = '/me'

/** How much of the token to show. Enough to see one was issued, not enough to
 *  be worth copying out of a screenshot. */
const TOKEN_PREVIEW_LENGTH = 24

interface SignedInState {
  result: SignInResult
  me: ApiUserAccount
}

/** The health of the API and of the database behind it. */
function HealthCard({ health }: { health: Loadable<HealthReport> }) {
  return (
    <Card title="GET /api/health">
      {health.state === 'loading' && (
        <p role="status" className="text-sm text-slate-soft">
          Calling {apiPath(HEALTH_ENDPOINT)}
        </p>
      )}
      {health.state === 'failed' && <FailureNotice error={health.error} what="The health check" />}
      {health.state === 'ready' && (
        <div>
          <FactRow
            label="The API answered"
            affirmative
            yes="Answered"
            no="Silent"
            detail={`status ${health.value.status}, environment ${health.value.environment}`}
          />
          <FactRow
            label="PostgreSQL is reachable"
            affirmative={health.value.databaseReachable}
            yes="Reachable"
            no="Unreachable"
            detail="The API opened a connection and ran a statement on it"
          />
          <FactRow
            label="btree_gist is installed"
            affirmative={health.value.btreeGistInstalled}
            yes="Installed"
            no="Missing"
            detail="Without it the exclusion constraint that prevents double booking cannot exist"
          />
        </div>
      )}
    </Card>
  )
}

/** Sign in for real, then call the protected endpoint with what came back. */
function IdentityCard({
  email,
  password,
  session,
  onEmailChange,
  onPasswordChange,
  onSubmit,
}: {
  email: string
  password: string
  session: Loadable<SignedInState>
  onEmailChange: (value: string) => void
  onPasswordChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  const busy = session.state === 'loading'
  return (
    <Card title={`POST ${apiPath(SIGN_IN_ENDPOINT)} then GET ${apiPath(ME_ENDPOINT)}`}>
      <form noValidate onSubmit={onSubmit} className="flex flex-col gap-md">
        <TextField
          id="system-email"
          label="Email address"
          type="email"
          inputMode="email"
          autoComplete="username"
          value={email}
          onChange={onEmailChange}
          help="A seeded development account. Change it to prove a wrong one is refused."
        />
        <PasswordField
          id="system-password"
          label="Password"
          autoComplete="current-password"
          value={password}
          onChange={onPasswordChange}
        />
        <div>
          <button type="submit" className="btn-primary px-lg" disabled={busy}>
            {busy ? 'Signing in' : 'Sign in against the API'}
          </button>
        </div>
      </form>

      {session.state === 'failed' && (
        <div className="mt-md">
          <FailureNotice error={session.error} what="The sign in" />
        </div>
      )}

      {session.state === 'ready' && (
        <div className="mt-md">
          <Notice tone="success" title="The protected endpoint answered">
            <p>
              The token issued by {apiPath(SIGN_IN_ENDPOINT)} was presented to{' '}
              {apiPath(ME_ENDPOINT)}, which loaded the account from PostgreSQL and read the role
              from the row rather than from the token.
            </p>
          </Notice>
          <div className="mt-md">
            <LiteralRow
              label="Access token"
              value={`${session.value.result.accessToken.slice(0, TOKEN_PREVIEW_LENGTH)}… (${
                session.value.result.tokenType
              }, expires in ${session.value.result.expiresIn} s)`}
            />
            <LiteralRow label="Name" value={session.value.me.name} />
            <LiteralRow label="Email" value={session.value.me.email} />
            <LiteralRow
              label="Branch"
              value={session.value.me.branchCode ?? 'none, which is correct for this role'}
            />
          </div>
          <div className="mt-sm flex flex-wrap items-center gap-sm">
            <StatusPill status="AVAILABLE" label={`Role ${session.value.me.role}`} />
            <StatusPill
              status={session.value.me.active ? 'AVAILABLE' : 'QUARANTINED'}
              label={session.value.me.active ? 'Active' : 'Deactivated'}
            />
          </div>
        </div>
      )}
    </Card>
  )
}

/** The point of the whole screen: the page origin and the request origin, side
 *  by side, read from the browser rather than asserted. */
function OriginCard() {
  const pageOrigin = window.location.origin
  const healthUrl = resolvedApiUrl(HEALTH_ENDPOINT)
  const requestOrigin = new URL(healthUrl).origin
  const sameOrigin = requestOrigin === pageOrigin

  return (
    <Card title="One origin, or two">
      <LiteralRow label="Origin of this page" value={pageOrigin} />
      <LiteralRow label="Path requested" value={apiPath(HEALTH_ENDPOINT)} />
      <LiteralRow label="Which the browser resolves to" value={healthUrl} />
      <LiteralRow label="Origin of that request" value={requestOrigin} />
      <div className="mt-md">
        <FactRow
          label="The page and the API share an origin"
          affirmative={sameOrigin}
          yes="Same origin"
          no="Cross origin"
          detail={
            sameOrigin
              ? 'No preflight is issued and SameSite=Strict can be honoured'
              : 'A relative base path cannot produce this. Something is pointing at an absolute origin.'
          }
        />
      </div>
    </Card>
  )
}

export default function SystemStatus() {
  const [health, setHealth] = useState<Loadable<HealthReport>>({ state: 'idle' })
  const [session, setSession] = useState<Loadable<SignedInState>>({ state: 'idle' })
  const [email, setEmail] = useState(SEEDED_EMAIL)
  const [password, setPassword] = useState(SEEDED_PASSWORD)

  const checkHealth = useCallback(async (): Promise<void> => {
    setHealth({ state: 'loading' })
    try {
      setHealth({ state: 'ready', value: await getHealth() })
    } catch (cause) {
      setHealth({ state: 'failed', error: asApiError(cause, apiPath(HEALTH_ENDPOINT)) })
    }
  }, [])

  useEffect(() => {
    void checkHealth()
  }, [checkHealth])

  async function handleSignIn(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setSession({ state: 'loading' })
    try {
      const result = await signIn(email, password)
      const me = await getCurrentUser(result.accessToken)
      setSession({ state: 'ready', value: { result, me } })
    } catch (cause) {
      setSession({ state: 'failed', error: asApiError(cause, apiPath(SIGN_IN_ENDPOINT)) })
    }
  }

  return (
    <>
      <PageHeader
        screenId="DEV-01"
        title="System connectivity"
        subtitle="Proves that the browser reaches the API through one origin, that the database answers, and that a real credential opens a protected endpoint."
        actions={
          <button type="button" className="btn-secondary px-md" onClick={() => void checkHealth()}>
            Check again
          </button>
        }
      />

      <DevelopmentScreenBanner>
        <p>
          This screen is not part of the twenty four assessed screens. SC-01 to SC-24 are the
          documented inventory and they read from fixtures, as Task 1 requires. This one exists to
          prove the path from the browser to PostgreSQL, and it is excluded from the screenshot
          capture that feeds the document appendix.
        </p>
      </DevelopmentScreenBanner>

      <div className="flex flex-col gap-lg">
        <OriginCard />
        <HealthCard health={health} />
        <IdentityCard
          email={email}
          password={password}
          session={session}
          onEmailChange={setEmail}
          onPasswordChange={setPassword}
          onSubmit={(event) => void handleSignIn(event)}
        />
      </div>
    </>
  )
}
