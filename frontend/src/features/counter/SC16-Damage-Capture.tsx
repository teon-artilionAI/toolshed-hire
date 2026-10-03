/**
 * SC-16 Damage Report Capture.
 *
 * Reached from the return inspection when a unit comes back worse than it went
 * out, with the unit of the hire in the address, or from the locator for a
 * unit that is out of service. The address carries the tag of the unit, and
 * the screen finds the unit through the locator route, which says where it is
 * and what state it is in. Under it are the reports already filed against the
 * unit, and the form for a new one.
 *
 * Filing a report takes the unit out of service at once. It moves to
 * quarantine and cannot be booked until the owner resolves the report, which
 * is the whole point of capturing it at the counter rather than in a notebook.
 * When the unit came back on a hire, the report can charge the customer, and
 * filing it settles the deposit of that hire unless something else is waiting.
 *
 * A signed in administrator also sees the owner's moves on each open report.
 * Nobody else does. Every write shows the server's answer in a notice that
 * takes focus.
 */

import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { DamageReport, LocatedUnit } from '../../shared/api/contract'
import { locatorQueries } from '../../shared/api/counter-queries'
import { damageQueries } from '../../shared/api/damage-queries'
import { MAX_LOCATOR_SEARCH_LENGTH, MIN_LOCATOR_SEARCH_LENGTH } from '../../shared/api/locator'
import { isRefusal } from '../../shared/api/problem-fields'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { Notice, PageHeader, StatusPill } from '../../shared/ui'
import { useSession } from '../../shared/use-session'
import { ASSET_STATUS_LABEL } from './counter-labels'
import { RENTAL_ITEM_PARAMETER } from './counter-links'
import { knownReplacementValue } from './SC16-damage-model'
import { DamageForm } from './SC16-Damage-Form'
import { DamageRecorded } from './SC16-DamageRecorded'
import { ReportHistory } from './SC16-Report-History'

const TITLE = 'Record damage'

const LOCATOR_PATH = '/counter/locator'

/** The most units one page of the locator holds. A tag is matched in part, so
 *  the unit is looked for among every unit the first page can carry. */
const UNIT_LOOKUP_PAGE_SIZE = 50

const FIRST_PAGE = 1

const LOADING_BLOCKS = 2

/** Tags are written in capitals, and a tag typed into the address may not be. */
function sameTag(found: string, asked: string): boolean {
  return found.toUpperCase() === asked.toUpperCase()
}

/** The locator, searching for this unit, so Cancel lands where it can be found again. */
function locatorFor(assetTag: string): string {
  return `${LOCATOR_PATH}?q=${encodeURIComponent(assetTag)}`
}

function NotFound({ assetTag }: { assetTag: string }) {
  return (
    <>
      <PageHeader screenId="SC-16" title={TITLE} subtitle="We could not find that unit." />
      <Notice tone="error" title={`No unit has the tag "${assetTag}"`}>
        <p>
          Check the tag on the unit itself. It is on the metal plate near the handle. If the tag is missing or
          unreadable, look the unit up by its model in the asset locator.
        </p>
        <Link to={LOCATOR_PATH} className="btn-secondary mt-sm px-md">
          Open the asset locator
        </Link>
      </Notice>
    </>
  )
}

/** The screen once the unit is known. */
function DamageScreen({ unit, rentalItemId }: { unit: LocatedUnit; rentalItemId: string | null }) {
  const { role, user } = useSession()
  const reports = useQuery(damageQueries.forUnit(unit.assetTag))
  const [filed, setFiled] = useState<DamageReport | null>(null)
  const elsewhere = role === 'counter' && user !== null && user.branchCode !== unit.branchCode

  // Filing replaces the form, so focus goes to what it did.
  const filedRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (filed !== null) filedRef.current?.focus()
  }, [filed])

  return (
    <div className="flex flex-col gap-lg">
      {elsewhere && filed === null && (
        <Notice tone="warn" title={`${unit.assetTag} is held at ${unit.branchName}`}>
          <p>
            A damage report is filed by the branch that holds the unit, so the server refuses one from this counter.
            Ring {unit.branchName}, or ask the owner to file it.
          </p>
        </Notice>
      )}
      {rentalItemId !== null && filed === null && (
        <Notice tone="info" title="This unit came back on a hire">
          <p>
            The deposit of that hire waits for this report. Filing it settles the deposit, unless something else on
            the hire is still waiting.
          </p>
        </Notice>
      )}
      <ReportHistory assetTag={unit.assetTag} ownerSignedIn={role === 'admin'} />
      {filed === null ? (
        <DamageForm
          unit={unit}
          rentalItemId={rentalItemId}
          replacementValue={knownReplacementValue(reports.data?.items ?? [], rentalItemId)}
          locatorHref={locatorFor(unit.assetTag)}
          onFiled={setFiled}
        />
      ) : (
        <DamageRecorded report={filed} noticeRef={filedRef} locatorHref={locatorFor(unit.assetTag)} />
      )}
    </div>
  )
}

export default function DamageReportCapture() {
  const { assetTag = '' } = useParams()
  const [params] = useSearchParams()
  const tag = assetTag.trim()
  const rentalItemId = params.get(RENTAL_ITEM_PARAMETER)?.trim() || null
  const searchable = tag.length >= MIN_LOCATOR_SEARCH_LENGTH && tag.length <= MAX_LOCATOR_SEARCH_LENGTH
  const lookup = useQuery({
    ...locatorQueries.search({ q: tag, page: FIRST_PAGE, pageSize: UNIT_LOOKUP_PAGE_SIZE }),
    enabled: searchable,
  })
  const phase = queryPhase(lookup)
  const unit = lookup.data?.items.find((candidate) => sameTag(candidate.assetTag, tag))

  // The locator refuses a search it cannot run with a 422, and to the
  // assistant that is the same as a tag nobody has.
  const notFound = !searchable || (phase === 'ready' && unit === undefined) || (phase === 'failed' && isRefusal(lookup.error))
  if (notFound) return <NotFound assetTag={tag} />

  return (
    <>
      <PageHeader
        screenId="SC-16"
        title={TITLE}
        subtitle={unit ? `${unit.assetTag}, ${unit.modelName}, at ${unit.branchName}.` : undefined}
        actions={unit ? <StatusPill status={unit.status} label={ASSET_STATUS_LABEL[unit.status]} /> : undefined}
      />
      {phase === 'failed' && (
        <div className="mb-lg">
          <ErrorState
            what={unit === undefined ? 'this unit' : 'the latest state of this unit'}
            error={lookup.error}
            onRetry={() => void lookup.refetch()}
          />
        </div>
      )}
      {unit !== undefined ? (
        // A read again that fails leaves the unit as it was last read, and the
        // failure above says so. A report being filed is never thrown away.
        <DamageScreen key={unit.assetTag} unit={unit} rentalItemId={rentalItemId} />
      ) : (
        phase !== 'failed' && <LoadingState label="Finding the unit" shape="rows" count={LOADING_BLOCKS} />
      )}
    </>
  )
}
