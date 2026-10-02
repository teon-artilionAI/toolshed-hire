/**
 * What SC-07 says around its list, when there is something to say.
 *
 * One note is about the bookings the list leaves out. A basket that was priced
 * and never held is kept by the server as a reservation that was not finished.
 * The list does not show those until the filter asks for them, and the note
 * says how many there are and offers them.
 *
 * The other is what stands where the table would be when there is no row to
 * draw. Each reason has its own words and its own way forward, so a person is
 * never left looking at an empty card.
 */

import { Link } from 'react-router-dom'
import { EmptyState } from '../../shared/ui'

/**
 * Why the list has no row to draw.
 *
 * - `none`: the customer has made no booking.
 * - `noneWithStatus`: no booking has the status the filter asks for.
 * - `pastTheEnd`: the address asks for a page after the last one.
 * - `unfinishedFillThePage`: every row of this page was left unfinished, and
 *   the bookings that were made are on other pages.
 */
export type NothingToListReason = 'none' | 'noneWithStatus' | 'pastTheEnd' | 'unfinishedFillThePage'

/** Says that unfinished bookings were left out, and offers to show them. */
export function UnfinishedLeftOut({ count, onShow }: { count: number; onShow: () => void }) {
  const one = count === 1
  return (
    <div className="mb-md flex flex-wrap items-center gap-x-md gap-y-sm text-sm text-slate-soft">
      <p>
        {count} {one ? 'booking' : 'bookings'} you started and did not finish{' '}
        {one ? 'is' : 'are'} left out of this list.
      </p>
      <button type="button" className="btn-ghost px-sm" onClick={onShow}>
        Show {one ? 'it' : 'them'}
        <span className="sr-only">, the bookings that were not finished</span>
      </button>
    </div>
  )
}

export function NothingToList({
  reason,
  onFirstPage,
  onClearFilter,
}: {
  reason: NothingToListReason
  onFirstPage: () => void
  onClearFilter: () => void
}) {
  return (
    <div className="card">
      {reason === 'pastTheEnd' && (
        <EmptyState
          title="That page is past the end of your bookings"
          body="There are fewer pages than the address asked for."
          action={
            <button type="button" className="btn-secondary px-md" onClick={onFirstPage}>
              Go to the first page
            </button>
          }
        />
      )}
      {reason === 'noneWithStatus' && (
        <EmptyState
          title="No bookings have that status"
          body="Try a different status, or clear the filter to see every booking."
          action={
            <button type="button" className="btn-secondary px-md" onClick={onClearFilter}>
              Clear the filter
            </button>
          }
        />
      )}
      {reason === 'unfinishedFillThePage' && (
        <EmptyState
          title="Nothing on this page was finished"
          body="Every booking on this page was started and not finished, so it is left out. Your other bookings are on the other pages."
        />
      )}
      {reason === 'none' && (
        <EmptyState
          title="You have no bookings yet"
          body="When you book equipment it appears here, with the collection branch and the dates."
          action={
            <Link to="/" className="btn-primary px-md">
              Browse the catalogue
            </Link>
          }
        />
      )}
    </div>
  )
}
