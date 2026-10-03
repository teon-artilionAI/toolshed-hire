/**
 * SC-15 Return and Condition Inspection.
 *
 * The counter side of taking equipment back, for one hire. The address carries
 * the hire's key or its reference, and the screen reads the hire from
 * `GET /api/rentals/{id}`. Every figure on it is the server's. The late fee of
 * each unit still out is what the server says it would be if the unit came back
 * today, and the screen says the system worked it out and the counter cannot
 * change it.
 *
 * The assistant ticks the units that are back on the counter and records how
 * each came back. One button asks the question, which says in words what is
 * about to happen, and one button answers it and posts the ticked units. The
 * answer is the hire as the server now has it, and the screen shows that.
 * While units are still out it says the hire is partially returned. Once the
 * last unit is back it shows the settlement from the server's figures, and
 * whatever the deposit is still waiting on.
 *
 * What a write did is said at the top in a notice that takes focus, so a
 * keyboard or screen reader user hears it without looking for it.
 */

import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { Rental } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { rentalQueries } from '../../shared/api/rental-queries'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate, money } from '../../shared/format'
import { Card, Notice, PageHeader, StatTile, StatusPill } from '../../shared/ui'
import { RENTAL_STATUS_LABEL, countOf } from './counter-labels'
import { OVERDUE_PATH } from './counter-links'
import { isNotFound } from './counter-refusal'
import { ReturnedItem } from './SC15-ItemInspection'
import { ReturnForm } from './SC15-Return-Form'
import { itemsOut } from './SC15-return-model'
import { SettlementSummary } from './SC15-SettlementSummary'

const TITLE = 'Return and condition inspection'

/** What the last write did, with the hire it answered with. */
interface Outcome {
  kind: 'returned' | 'paid'
  rental: Rental
}

/** What a write did, in words, from the hire the server answered with. */
function outcomeWords({ kind, rental }: Outcome): { title: string; body: string } {
  const out = itemsOut(rental).length
  if (kind === 'paid') {
    return { title: `${rental.reference} is settled`, body: 'The payment of the balance is recorded.' }
  }
  if (out > 0) {
    return {
      title: `${rental.reference} is partially returned`,
      body: `${countOf(out, 'unit is', 'units are')} still out, so the deposit stays held.`,
    }
  }
  const after =
    rental.settlementWaitingOn === 'BALANCE_PAYMENT'
      ? 'The deposit did not cover the charges, so a balance is due.'
      : rental.settlementWaitingOn === 'DAMAGE_ASSESSMENT'
        ? 'The deposit is waiting for a damage report.'
        : 'The deposit is settled below.'
  return { title: `Every unit on ${rental.reference} is back`, body: after }
}

function NotFound({ rentalKey }: { rentalKey: string }) {
  return (
    <>
      <PageHeader screenId="SC-15" title="We cannot find that hire" />
      <Notice tone="error" title={`No hire matches "${rentalKey}"`}>
        <p>Check the reference on the customer's paperwork, or open the overdue worklist and start the return from there.</p>
        <Link to={OVERDUE_PATH} className="btn-secondary mt-sm px-md">
          Open the overdue worklist
        </Link>
      </Notice>
    </>
  )
}

/** Where the hire stands while units are still out. */
function StillOut({ rental }: { rental: Rental }) {
  const out = itemsOut(rental).length
  if (out === rental.items.length) {
    return (
      <Notice tone="info" title={`Every unit on ${rental.reference} is still out`}>
        <p>The deposit of {money(rental.depositHeld)} stays held until the last unit is back.</p>
      </Notice>
    )
  }
  return (
    <Notice tone="warn" title={`${rental.reference} is partially returned`}>
      <p>
        {out} of {countOf(rental.items.length, 'unit is', 'units are')} still out. The deposit of{' '}
        {money(rental.depositHeld)} stays held until the last one is back.
      </p>
    </Notice>
  )
}

function ReturnView({
  rental,
  onWritten,
  onReload,
}: {
  rental: Rental
  onWritten: (outcome: Outcome) => void
  onReload: () => void
}) {
  const out = itemsOut(rental)
  const back = rental.items.filter((item) => item.returnedAt !== null)
  return (
    <div className="flex flex-col gap-lg">
      <div className="grid gap-md sm:grid-cols-3">
        <StatTile
          label="Due back"
          value={formatDate(rental.dueBackOn)}
          tone={rental.status === 'OVERDUE' ? 'bad' : 'default'}
          hint={rental.status === 'OVERDUE' ? 'Overdue' : `Out since ${formatDate(rental.from)}`}
        />
        <StatTile
          label="Units still out"
          value={out.length}
          tone={out.length > 0 ? 'warn' : 'good'}
          hint={`${countOf(rental.items.length, 'unit', 'units')} on this hire`}
        />
        <StatTile label="Deposit held" value={money(rental.depositHeld)} hint="Taken at collection" />
      </div>

      {out.length > 0 && <StillOut rental={rental} />}

      {out.length > 0 && !rental.canReturn && (
        <Notice tone="warn" title="These units cannot be taken back here">
          <p>
            The server does not offer a return on this hire to this account. A hire is taken back at{' '}
            {rental.branchName}, the branch it went out from.
          </p>
        </Notice>
      )}

      {out.length > 0 && rental.canReturn && (
        <ReturnForm
          key={rental.id}
          rental={rental}
          onReturned={(answered) => onWritten({ kind: 'returned', rental: answered })}
          onReload={onReload}
        />
      )}

      {back.length > 0 && (
        <Card title="Units already back">
          <ul className="flex flex-col gap-md">
            {back.map((item) => (
              <li key={item.id}>
                <ReturnedItem item={item} charges={rental.charges} />
              </li>
            ))}
          </ul>
        </Card>
      )}

      {out.length === 0 && (
        <SettlementSummary rental={rental} onPaid={(answered) => onWritten({ kind: 'paid', rental: answered })} />
      )}
    </div>
  )
}

export default function ReturnAndConditionInspection() {
  const { rentalId = '' } = useParams()
  const hire = useQuery({ ...rentalQueries.detail(rentalId), enabled: rentalId !== '' })
  const phase = queryPhase(hire)
  const data = hire.data
  const [outcome, setOutcome] = useState<Outcome | null>(null)

  // A write replaces part of the screen, so focus goes to what it did.
  const outcomeRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (outcome !== null) outcomeRef.current?.focus()
  }, [outcome])

  if (phase === 'failed' && isNotFound(hire.error)) return <NotFound rentalKey={rentalId} />

  const words = outcome === null ? null : outcomeWords(outcome)
  return (
    <>
      <PageHeader
        screenId="SC-15"
        title={TITLE}
        subtitle={
          data
            ? `${data.reference} for ${data.customerName}, ${data.customerPhone}. Out from ${data.branchName} on ${formatDate(data.from)}, due back ${formatDate(data.dueBackOn)}.`
            : undefined
        }
        actions={data ? <StatusPill status={data.status} label={RENTAL_STATUS_LABEL[data.status]} /> : undefined}
      />

      <div ref={outcomeRef} tabIndex={-1} className="mb-lg empty:hidden">
        {words !== null && (
          <Notice tone="success" title={words.title}>
            <p>{words.body}</p>
          </Notice>
        )}
      </div>

      {phase === 'failed' ? (
        <ErrorState what="this hire" error={hire.error} onRetry={() => void hire.refetch()} />
      ) : data === undefined ? (
        <LoadingState label="Loading the hire" shape="detail" count={2} />
      ) : (
        <div aria-busy={hire.isFetching}>
          <ReturnView rental={data} onWritten={setOutcome} onReload={() => void hire.refetch()} />
        </div>
      )}
    </>
  )
}
