/**
 * The three lists behind the figures on SC-10.
 *
 * A number on a dashboard that cannot be opened is a number nobody trusts, so
 * every figure that asks for something to be done has its list here, and every
 * entry ends in the screen that does it. A collection goes to the checkout of
 * its booking. A return and an overdue hire go to the return screen of the
 * hire.
 *
 * The days late and the late fee on an overdue hire are the server's, shown as
 * it sent them. The browser works out no fee.
 *
 * The server sends at most fifty of each, with the true count beside them. A
 * list that is shorter than its count says how many it shows, and the diary
 * lists every booking and every hire of a day.
 */

import type {
  CounterDashboard,
  DashboardCollection,
  DashboardOverdue,
  DashboardReturn,
} from '../../shared/api/contract'
import { formatDate, money } from '../../shared/format'
import { Card, StatusPill } from '../../shared/ui'
import { CardLink, CounterEntry, EntryLink } from './counter-entry'
import { countOf } from './counter-labels'
import { DIARY_PATH, checkoutHref, rentalHref } from './counter-links'

/** Said under a list the server cut short. */
function CutShort({ shown, total }: { shown: number; total: number }) {
  if (shown >= total) return null
  return (
    <p className="mt-md text-sm text-slate-soft">
      Showing the first {shown} of {total}.
    </p>
  )
}

/** Said in place of a list with nothing in it. */
function NothingHere({ children }: { children: string }) {
  return <p className="text-sm text-slate-soft">{children}</p>
}

function CollectionEntry({ collection }: { collection: DashboardCollection }) {
  return (
    <CounterEntry
      reference={collection.reference}
      customerName={collection.customerName}
      customerPhone={collection.customerPhone}
      actions={
        <EntryLink to={checkoutHref(collection.reference)} reference={collection.reference} primary>
          Check out
        </EntryLink>
      }
    >
      <p>{collection.summary}</p>
      <p className="tabular text-slate-soft">
        {countOf(collection.unitCount, 'unit', 'units')}, {formatDate(collection.from)} to {formatDate(collection.to)}
      </p>
    </CounterEntry>
  )
}

function ReturnEntry({ rental }: { rental: DashboardReturn }) {
  return (
    <CounterEntry
      reference={rental.reference}
      customerName={rental.customerName}
      customerPhone={rental.customerPhone}
      actions={
        <EntryLink to={rentalHref(rental.rentalId)} reference={rental.reference}>
          Take the return
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

function OverdueEntry({ rental }: { rental: DashboardOverdue }) {
  return (
    <CounterEntry
      reference={rental.reference}
      status={<StatusPill status="OVERDUE" label={`${countOf(rental.daysOverdue, 'day', 'days')} late`} />}
      customerName={rental.customerName}
      customerPhone={rental.customerPhone}
      actions={
        <EntryLink to={rentalHref(rental.rentalId)} reference={rental.reference}>
          Take the return
        </EntryLink>
      }
    >
      <p className="tabular">
        Was due back {formatDate(rental.dueBackOn)}, {countOf(rental.itemsOut, 'unit', 'units')} still out
      </p>
      <p className="tabular">
        Late fee so far <span className="font-semibold">{money(rental.lateFeeAccrued)}</span>
      </p>
    </CounterEntry>
  )
}

export function TodayLists({ dashboard }: { dashboard: CounterDashboard }) {
  const { counts, collectionsDue, returnsDue, overdue } = dashboard
  return (
    <div className="flex flex-col gap-lg">
      <Card title="Going out today" action={<CardLink to={DIARY_PATH}>Open the diary</CardLink>}>
        {collectionsDue.length === 0 ? (
          <NothingHere>Nobody is booked to collect today.</NothingHere>
        ) : (
          <ul aria-label="Collections due today">
            {collectionsDue.map((collection) => (
              <CollectionEntry key={collection.reservationId} collection={collection} />
            ))}
          </ul>
        )}
        <CutShort shown={collectionsDue.length} total={counts.collectionsDue} />
      </Card>

      <Card title="Due back today" action={<CardLink to={DIARY_PATH}>Open the diary</CardLink>}>
        {returnsDue.length === 0 ? (
          <NothingHere>Nothing is due back today.</NothingHere>
        ) : (
          <ul aria-label="Returns due today">
            {returnsDue.map((rental) => (
              <ReturnEntry key={rental.rentalId} rental={rental} />
            ))}
          </ul>
        )}
        <CutShort shown={returnsDue.length} total={counts.returnsDue} />
      </Card>

      <Card title="Overdue hires">
        {overdue.length === 0 ? (
          <NothingHere>Nothing is late. Every hire is back or still in date.</NothingHere>
        ) : (
          <ul aria-label="Overdue hires">
            {overdue.map((rental) => (
              <OverdueEntry key={rental.rentalId} rental={rental} />
            ))}
          </ul>
        )}
        <CutShort shown={overdue.length} total={counts.overdue} />
      </Card>
    </div>
  )
}
