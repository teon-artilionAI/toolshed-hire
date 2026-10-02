/**
 * DEV-01 System Connectivity.
 *
 * WHY THIS SCREEN EXISTS
 * ======================
 * The whole design rests on the browser seeing a single origin, with `/api/*`
 * rewritten to Cloud Run server side and a refresh cookie that can honestly be
 * `SameSite=Strict`. That is precisely the kind of decision that works locally
 * and fails in production, or the reverse. I wanted a page that shows it
 * happening, so nobody has to take it on trust.
 *
 * This screen does that and nothing more. It calls the real health endpoint,
 * calls the protected `/api/me` as whoever is signed in, and shows the origin
 * the browser actually used next to the path it actually requested, so a
 * reader can see for themselves that they are the same origin.
 *
 * IT HAS NO SIGN IN OF ITS OWN
 * ============================
 * It used to sign in by itself, outside the session, with a seeded account
 * written into the page. Now it uses the session like every other screen. A
 * person signs in on the sign in screen and comes back, and the call to
 * `/api/me` carries the token of the session through the client. The screen
 * never sees that token, which is the point of where the session keeps it.
 *
 * IT IS NOT A SCREEN OF THE PRODUCT
 * =================================
 * SC-01 to SC-24 are the screens of the product. This one is DEV-01,
 * deliberately outside that series, and it is in no navigation menu.
 *
 * The API is often not running while the interface is being worked on, so
 * every call here fails into an explanation and not a blank page.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, Notice, PageHeader, StatusPill } from '../../shared/ui'
import { asApiError } from '../../shared/api-problem'
import { getCurrentUser } from '../../shared/api/auth'
import { apiPath, resolvedApiUrl } from '../../shared/api/client'
import type { HealthReport, SessionUser } from '../../shared/api/contract'
import { getHealth } from '../../shared/api/system'
import { signInAddress } from '../../shared/screen-access'
import { useSession } from '../../shared/use-session'
import {
  DevelopmentScreenBanner,
  FactRow,
  FailureNotice,
  LiteralRow,
} from './system-panels'
import type { Loadable } from './system-panels'

const HEALTH_ENDPOINT = '/health'
const ME_ENDPOINT = '/me'

/** The address of this screen, so signing in brings the person back here. */
const SYSTEM_PATH = '/system'

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
            detail={`status ${health.value.status}, environment ${health.value.environment}, revision ${health.value.revision}`}
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

/** One account, as `/api/me` reports it. */
function AccountRows({ account }: { account: SessionUser }) {
  return (
    <>
      <LiteralRow label="Name" value={account.fullName} />
      <LiteralRow label="Email" value={account.email} />
      <LiteralRow
        label="Branch"
        value={account.branchCode ?? 'none, which is correct for this role'}
      />
      <div className="mt-sm flex flex-wrap items-center gap-sm">
        <StatusPill status="AVAILABLE" label={`Role ${account.role}`} />
        <StatusPill
          status={account.emailVerified ? 'AVAILABLE' : 'RESERVED'}
          label={account.emailVerified ? 'Email verified' : 'Email not verified'}
        />
      </div>
    </>
  )
}

/** Call the protected endpoint as whoever the session says is signed in. */
function IdentityCard({
  me,
  onCallAgain,
}: {
  me: Loadable<SessionUser>
  onCallAgain: () => void
}) {
  const { user } = useSession()

  if (!user) {
    return (
      <Card title={`The session, then GET ${apiPath(ME_ENDPOINT)}`}>
        <Notice tone="info" title="Nobody is signed in">
          <p>
            This card calls the protected endpoint with the token the session holds, so it needs a
            session. Sign in and you are brought straight back here.
          </p>
        </Notice>
        <Link to={signInAddress(SYSTEM_PATH)} className="btn-primary mt-md px-md">
          Sign in
        </Link>
      </Card>
    )
  }

  const calling = me.state === 'loading'
  return (
    <Card title={`The session, then GET ${apiPath(ME_ENDPOINT)}`}>
      <p className="text-sm text-slate-soft">
        The session holds an access token in memory and this screen cannot read it. The client
        attaches it to the call below.
      </p>
      <button
        type="button"
        className="btn-secondary mt-md px-md"
        onClick={onCallAgain}
        disabled={calling}
      >
        {calling ? 'Calling' : `Call ${apiPath(ME_ENDPOINT)} again`}
      </button>

      {me.state === 'failed' && (
        <div className="mt-md">
          <FailureNotice error={me.error} what="The call to the protected endpoint" />
        </div>
      )}

      {me.state === 'ready' && (
        <div className="mt-md">
          <Notice tone="success" title="The protected endpoint answered">
            <p>
              The token the session holds was presented to {apiPath(ME_ENDPOINT)}, which loaded the
              account from PostgreSQL and read the role from the row and not from the token.
            </p>
          </Notice>
          <div className="mt-md">
            <AccountRows account={me.value} />
          </div>
        </div>
      )}
    </Card>
  )
}

/** The point of the whole screen. The page origin and the request origin, side
 *  by side, read from the browser and not asserted. */
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
  const { user } = useSession()
  const [health, setHealth] = useState<Loadable<HealthReport>>({ state: 'idle' })
  const [me, setMe] = useState<Loadable<SessionUser>>({ state: 'idle' })
  const signedInUserId = user?.id ?? null

  const checkHealth = useCallback(async (): Promise<void> => {
    setHealth({ state: 'loading' })
    try {
      setHealth({ state: 'ready', value: await getHealth() })
    } catch (cause) {
      setHealth({ state: 'failed', error: asApiError(cause, apiPath(HEALTH_ENDPOINT)) })
    }
  }, [])

  const checkIdentity = useCallback(async (): Promise<void> => {
    setMe({ state: 'loading' })
    try {
      setMe({ state: 'ready', value: await getCurrentUser() })
    } catch (cause) {
      setMe({ state: 'failed', error: asApiError(cause, apiPath(ME_ENDPOINT)) })
    }
  }, [])

  useEffect(() => {
    void checkHealth()
  }, [checkHealth])

  // The protected call is made as soon as there is somebody to make it as, and
  // again when a different account signs in.
  useEffect(() => {
    if (signedInUserId === null) return
    void checkIdentity()
  }, [signedInUserId, checkIdentity])

  return (
    <>
      <PageHeader
        screenId="DEV-01"
        title="System connectivity"
        subtitle="Checks that the browser reaches the API through one origin, that the database answers, and that the session opens a protected endpoint."
        actions={
          <button type="button" className="btn-secondary px-md" onClick={() => void checkHealth()}>
            Check again
          </button>
        }
      />

      <DevelopmentScreenBanner>
        <p>
          This is a development page for checking connectivity. It is not a screen of the
          product and it is in no menu. It follows one request from the browser, through the
          API, to PostgreSQL and back.
        </p>
      </DevelopmentScreenBanner>

      <div className="flex flex-col gap-lg">
        <OriginCard />
        <HealthCard health={health} />
        <IdentityCard me={me} onCallAgain={() => void checkIdentity()} />
      </div>
    </>
  )
}
