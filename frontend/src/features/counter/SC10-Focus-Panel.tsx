/**
 * The list behind each figure on SC-10.
 *
 * A number on a dashboard that cannot be opened is a number nobody trusts.
 * Every tile on the counter dashboard opens its own list here, and every
 * list ends in a link to the screen that does the work.
 */

import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Card, DataTable, EmptyState, StatusPill } from '../../shared/ui'
import { formatDate, money } from '../../shared/format'
import type { Asset } from '../../shared/types'
import * as desk from './counter-desk-data'

export type FocusId = 'collections' | 'returns' | 'overdue' | 'quarantine' | 'reallocate'

export function PanelLink({ to, children }: { to: string; children: string }) {
  return (
    <Link to={to} className="btn-ghost px-sm text-sm">
      {children}
      <ArrowRight className="h-4 w-4" aria-hidden="true" />
    </Link>
  )
}

/** What the tiles count, and what each drill-through panel reads from. */
export interface TodayData {
  collections: desk.CollectionEntry[]
  waiting: desk.CollectionEntry[]
  returns: desk.ReturnEntry[]
  stillOut: desk.ReturnEntry[]
  overdue: desk.ReturnEntry[]
  quarantined: Asset[]
  reallocate: desk.ReallocationFlag[]
  onHire: Asset[]
  available: Asset[]
  weekCollections: number
}

export default function FocusPanel({ focus, today }: { focus: FocusId; today: TodayData }) {
  if (focus === 'collections') {
    return (
      <Card title="Going out today" action={<PanelLink to="/counter/diary">See the diary</PanelLink>}>
        {today.collections.length === 0 ? (
          <EmptyState
            title="Nothing booked for collection today"
            body="Bookings for other days are in the diary."
          />
        ) : (
          <DataTable
            caption="Bookings due for collection today"
            columns={['Booking', 'Customer', 'Tools', 'Where it stands']}
          >
            {today.collections.map((entry) => (
              <tr key={entry.key}>
                <td className="td font-mono">{entry.reservation.reference}</td>
                <td className="td">{entry.customer.name}</td>
                <td className="td">{entry.headline}</td>
                <td className="td">
                  {entry.rental ? (
                    <StatusPill status="COLLECTED" label="Handed over" />
                  ) : (
                    <StatusPill
                      status={entry.reservation.status}
                      label={
                        entry.reservation.status === 'NO_SHOW'
                          ? 'Did not arrive'
                          : 'Waiting for collection'
                      }
                    />
                  )}
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </Card>
    )
  }

  if (focus === 'returns') {
    return (
      <Card title="Due back today" action={<PanelLink to="/counter/diary">See the diary</PanelLink>}>
        {today.returns.length === 0 ? (
          <EmptyState
            title="Nothing due back today"
            body="Anything already late is under Overdue now."
          />
        ) : (
          <DataTable
            caption="Hires due back today"
            columns={['Booking', 'Customer', 'Tools', 'Where it stands']}
          >
            {today.returns.map((entry) => (
              <tr key={entry.key}>
                <td className="td font-mono">
                  {entry.rental?.reference ?? entry.reservation.reference}
                </td>
                <td className="td">{entry.customer.name}</td>
                <td className="td">{entry.headline}</td>
                <td className="td">
                  <StatusPill
                    status={entry.collected ? 'OPEN' : 'CONFIRMED'}
                    label={entry.collected ? 'Out with the customer' : 'Not collected yet'}
                  />
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </Card>
    )
  }

  if (focus === 'overdue') {
    return (
      <Card
        title="Overdue now"
        action={<PanelLink to="/counter/overdue">Work through these</PanelLink>}
      >
        {today.overdue.length === 0 ? (
          <EmptyState title="Nothing is late" body="Every hire is either back or still in date." />
        ) : (
          <DataTable
            caption="Hires past their due date"
            columns={['Hire', 'Customer', 'Was due', 'Days late', 'Late fees so far']}
          >
            {today.overdue.map((entry) => (
              <tr key={entry.key}>
                <td className="td font-mono">
                  {entry.rental?.reference ?? entry.reservation.reference}
                </td>
                <td className="td">{entry.customer.name}</td>
                <td className="td whitespace-nowrap">{formatDate(entry.dueOn)}</td>
                <td className="td tabular">{entry.daysLate}</td>
                <td className="td tabular font-mono">{money(desk.lateFeeRunning(entry))}</td>
              </tr>
            ))}
          </DataTable>
        )}
      </Card>
    )
  }

  if (focus === 'quarantine') {
    return (
      <Card
        title="Quarantined units"
        action={<PanelLink to="/counter/locator">Find these units</PanelLink>}
      >
        {today.quarantined.length === 0 ? (
          <EmptyState
            title="Nothing in quarantine"
            body="Every unit at this branch is serviceable and can go out."
          />
        ) : (
          <DataTable
            caption="Units withdrawn from hire"
            columns={['Asset tag', 'Model', 'Branch', 'Condition', 'Status']}
          >
            {today.quarantined.map((asset) => (
              <tr key={asset.id}>
                <td className="td font-mono">{asset.tag}</td>
                <td className="td">{desk.modelById(asset.productModelId).name}</td>
                <td className="td">{desk.branchByCode(asset.branchCode).name}</td>
                <td className="td">Grade {asset.condition}</td>
                <td className="td">
                  <StatusPill status={asset.status} label="Not hireable" />
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </Card>
    )
  }

  return (
    <Card
      title="Bookings to reallocate"
      action={<PanelLink to="/counter/booking">Open bookings</PanelLink>}
    >
      {today.reallocate.length === 0 ? (
        <EmptyState
          title="Every booking has a unit set aside"
          body="If a unit is withdrawn from service, the booking it was set aside for appears here."
        />
      ) : (
        <DataTable
          caption="Bookings that cannot go out as they stand"
          columns={['Booking', 'Customer', 'Dates', 'What needs doing']}
        >
          {today.reallocate.map((flag, index) => (
            <tr key={`${flag.reservation.id}-${index}`}>
              <td className="td font-mono">{flag.reservation.reference}</td>
              <td className="td">{flag.customer.name}</td>
              <td className="td whitespace-nowrap">
                {formatDate(flag.reservation.startDate)} to {formatDate(flag.reservation.endDate)}
              </td>
              <td className="td">{flag.reason}</td>
            </tr>
          ))}
        </DataTable>
      )}
    </Card>
  )
}
