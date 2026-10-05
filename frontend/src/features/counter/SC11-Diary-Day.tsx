/**
 * One day of the diary on SC-11, with what goes out and what comes back.
 *
 * The day view shows one of these and the week view shows seven, so a booking
 * reads the same and offers the same way forward in both. Each entry carries
 * its status in words as well as colour.
 *
 * A booking that is confirmed and starts today or earlier can go out now, so
 * it links to its checkout. A booking that has been collected or is back links
 * to its hire. The diary does not send the key of that hire, so the link goes
 * through the checkout of the booking, which says it is out and opens the
 * hire. A hire due back links to its return screen. Where the server says a
 * booking may be marked as a no show, the entry offers that too.
 */

import type { DiaryCollection, DiaryDay, DiaryReturn } from '../../shared/api/contract'
import { formatDate } from '../../shared/format'
import { StatusPill } from '../../shared/ui'
import { CounterEntry, EntryLink } from './counter-entry'
import { DIARY_COLLECTION_LABEL, RENTAL_STATUS_LABEL, countOf } from './counter-labels'
import { checkoutHref, rentalHref } from './counter-links'
import { dayName } from './diary-dates'
import NoShowAction from './SC11-No-Show-Action'

function CollectionActions({ collection, today }: { collection: DiaryCollection; today: string }) {
  if (collection.status === 'CONFIRMED' && collection.from <= today) {
    return (
      <EntryLink to={checkoutHref(collection.reference)} reference={collection.reference} primary>
        Check out
      </EntryLink>
    )
  }
  if (collection.status === 'COLLECTED' || collection.status === 'RETURNED') {
    return (
      <EntryLink to={checkoutHref(collection.reference)} reference={collection.reference}>
        Open the hire
      </EntryLink>
    )
  }
  return null
}

function CollectionEntry({ collection, today }: { collection: DiaryCollection; today: string }) {
  const actions = <CollectionActions collection={collection} today={today} />
  return (
    <CounterEntry
      reference={collection.reference}
      status={<StatusPill status={collection.status} label={DIARY_COLLECTION_LABEL[collection.status]} />}
      customerName={collection.customerName}
      customerPhone={collection.customerPhone}
      actions={actions}
      footer={<NoShowAction collection={collection} />}
    >
      <p>{collection.summary}</p>
      <p className="tabular text-slate-soft">
        {countOf(collection.unitCount, 'unit', 'units')},{' '}
        {collection.status === 'RETURNED' ? 'booked until' : 'due back'} {formatDate(collection.to)}
      </p>
    </CounterEntry>
  )
}

function ReturnEntry({ rental }: { rental: DiaryReturn }) {
  return (
    <CounterEntry
      reference={rental.reference}
      status={<StatusPill status={rental.status} label={RENTAL_STATUS_LABEL[rental.status]} />}
      customerName={rental.customerName}
      customerPhone={rental.customerPhone}
      actions={
        <EntryLink to={rentalHref(rental.rentalId)} reference={rental.reference}>
          Open the hire
        </EntryLink>
      }
    >
      <p>{rental.summary}</p>
      <p className="tabular text-slate-soft">
        {rental.itemsOut} of {countOf(rental.itemCount, 'unit', 'units')} still out
      </p>
    </CounterEntry>
  )
}

function ListHeading({ children }: { children: string }) {
  return <h3 className="mb-sm mt-md text-sm font-semibold uppercase tracking-wide text-slate-soft">{children}</h3>
}

export function DiaryDaySection({
  day,
  today,
  onOpenDay,
}: {
  day: DiaryDay
  /** Today at the branches, which decides what can go out now. */
  today: string
  /** Opens this day on its own. Left out when it is already on its own. */
  onOpenDay?: (date: string) => void
}) {
  const name = dayName(day.date)
  const headingId = `diary-day-${day.date}`
  return (
    <section aria-labelledby={headingId} className="card p-lg">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <h2 id={headingId} className="flex flex-wrap items-center gap-sm text-lg font-semibold text-ink">
          {name}
          {day.date === today && (
            <span className="rounded bg-accent px-sm py-xs text-xs font-semibold text-accent-ink">Today</span>
          )}
        </h2>
        {onOpenDay && (
          <button type="button" className="btn-ghost px-md" onClick={() => onOpenDay(day.date)}>
            Open this day <span className="sr-only">{name}</span>
          </button>
        )}
      </div>

      <ListHeading>Going out</ListHeading>
      {day.collections.length === 0 ? (
        <p className="text-sm text-slate-soft">Nothing goes out on this day.</p>
      ) : (
        <ul aria-label={`Going out on ${name}`}>
          {day.collections.map((collection) => (
            <CollectionEntry key={collection.reservationId} collection={collection} today={today} />
          ))}
        </ul>
      )}

      <ListHeading>Coming back</ListHeading>
      {day.returns.length === 0 ? (
        <p className="text-sm text-slate-soft">Nothing is due back on this day.</p>
      ) : (
        <ul aria-label={`Coming back on ${name}`}>
          {day.returns.map((rental) => (
            <ReturnEntry key={rental.rentalId} rental={rental} />
          ))}
        </ul>
      )}
    </section>
  )
}
