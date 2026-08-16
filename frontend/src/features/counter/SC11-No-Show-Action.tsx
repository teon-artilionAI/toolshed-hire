/**
 * The no-show control on SC-11.
 *
 * Marking a customer as not having arrived is the one destructive thing on
 * the diary, so it asks once before it does it, says what will happen, and
 * can be undone straight afterwards.
 */

import { formatDate } from '../../shared/format'

/**
 * Marking a no-show is the one destructive thing on this screen, so it asks
 * once before it does it and can be undone straight after.
 */
export default function NoShowAction({
  reservationId,
  reference,
  startDate,
  anchor,
  collected,
  markedHere,
  recordedInFixture,
  confirming,
  onAsk,
  onCancel,
  onConfirm,
  onUndo,
}: {
  reservationId: string
  reference: string
  startDate: string
  anchor: string
  collected: boolean
  markedHere: boolean
  recordedInFixture: boolean
  confirming: boolean
  onAsk: () => void
  onCancel: () => void
  onConfirm: () => void
  onUndo: () => void
}) {
  if (markedHere) {
    return (
      <div className="flex flex-col gap-xs">
        <button type="button" onClick={onUndo} className="btn-secondary">
          Undo no-show
        </button>
        <span className="text-xs text-slate-soft">Marked just now</span>
      </div>
    )
  }

  if (recordedInFixture) {
    return <span className="text-sm text-slate-soft">Recorded on the day</span>
  }

  if (collected) {
    return <span className="text-sm text-slate-soft">Nothing to do</span>
  }

  if (anchor < startDate) {
    return (
      <span className="text-sm text-slate-soft">
        You can mark this from {formatDate(startDate)}
      </span>
    )
  }

  if (confirming) {
    return (
      <div className="flex flex-col gap-sm">
        <p className="text-sm text-ink">Mark {reference} as a no-show?</p>
        <div className="flex flex-wrap gap-sm">
          <button
            type="button"
            onClick={onConfirm}
            className="btn-danger"
            aria-describedby={`noshow-note-${reservationId}`}
          >
            Yes, mark no-show
          </button>
          <button type="button" onClick={onCancel} className="btn-secondary">
            Keep the booking
          </button>
        </div>
        <span id={`noshow-note-${reservationId}`} className="text-xs text-slate-soft">
          The units go back on the shelf and the customer is told.
        </span>
      </div>
    )
  }

  return (
    <button type="button" onClick={onAsk} className="btn-secondary">
      Mark as no-show
    </button>
  )
}
