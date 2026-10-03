/**
 * The table the SC-07 list is drawn in.
 *
 * Six columns do not fit across a phone. A table that is wider than the
 * screen has to be scrolled sideways inside its box, and the status and the
 * total of every booking then sit out of sight. So below the `sm` width this
 * table is drawn as one block for each booking, with every value on a line of
 * its own and its heading beside it. From `sm` up it is an ordinary table.
 *
 * It is one table in the document at every width. Only how it is drawn
 * changes, through the classes here and in reservation-row.tsx. Changing how
 * a table is displayed can make a browser stop reporting it as a table, so
 * each part states its role, and a screen reader hears the same table either
 * way. The headings are hidden on a phone, which is why each value there
 * carries its own.
 */

import type { ReactNode } from 'react'
import { RESERVATION_COLUMNS } from './reservation-columns'

export function ReservationTable({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="table-wrap">
      <table role="table" className="block w-full border-collapse sm:table">
        <caption className="sr-only">{caption}</caption>
        <thead role="rowgroup" className="hidden border-b border-line bg-muted sm:table-header-group">
          <tr role="row">
            {RESERVATION_COLUMNS.map((column) => (
              <th key={column} role="columnheader" scope="col" className="th">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody role="rowgroup" className="block divide-y divide-line sm:table-row-group">
          {children}
        </tbody>
      </table>
    </div>
  )
}
