/**
 * The email delivery log on SC-24.
 *
 * A booking confirmation that never arrived is a customer standing at the
 * counter with nothing to show. So the log records the attempt, not just the
 * intention, and a failed attempt is the loudest thing on the row with the
 * one action that fixes it right next to it.
 */

import { useMemo, useState } from 'react'
import { Loader2, Send } from 'lucide-react'
import { formatDateTime, humanise } from '../../shared/format'
import type { NotificationRecord } from '../../shared/types'
import { DataTable, EmptyState, Field, StatusPill } from '../../shared/ui'

const SELECT_CLASS = 'field-input cursor-pointer transition-colors duration-200'

type DeliveryFilter = 'ALL' | 'DELIVERED' | 'FAILED'

export default function NotificationLog({
  records,
  sendingId,
  onResend,
}: {
  records: NotificationRecord[]
  sendingId: string | null
  onResend: (record: NotificationRecord) => void
}) {
  const [filter, setFilter] = useState<DeliveryFilter>('ALL')

  const shown = useMemo(
    () =>
      records
        .filter((r) =>
          filter === 'ALL'
            ? true
            : filter === 'DELIVERED'
              ? r.delivered
              : !r.delivered,
        )
        .sort((a, b) => b.at.localeCompare(a.at)),
    [records, filter],
  )

  return (
    <>
      <div className="mb-lg max-w-sm">
        <Field label="Delivery" htmlFor="delivery-filter">
          <select
            id="delivery-filter"
            className={SELECT_CLASS}
            value={filter}
            onChange={(e) => setFilter(e.target.value as DeliveryFilter)}
          >
            <option value="ALL">Every email we tried to send</option>
            <option value="DELIVERED">Arrived</option>
            <option value="FAILED">Did not arrive</option>
          </select>
        </Field>
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title="Nothing to show for that filter"
          body="Switch the delivery filter back to every email to see the full log."
          action={
            <button
              type="button"
              className="btn-secondary px-md"
              onClick={() => setFilter('ALL')}
            >
              Show every email
            </button>
          }
        />
      ) : (
        <DataTable
          columns={['When', 'Sent to', 'What it was', 'Booking', 'Delivery', 'Action']}
          caption="Every email the system has tried to send, and whether it arrived"
        >
          {shown.map((record) => {
            const sending = sendingId === record.id
            return (
              <tr
                key={record.id}
                className={`transition-colors duration-200 hover:bg-muted ${
                  record.delivered ? '' : 'bg-status-overdue-wash'
                }`}
              >
                <th scope="row" className="td whitespace-nowrap text-left font-normal">
                  <span className="tabular font-mono text-xs text-ink">
                    {formatDateTime(record.at)}
                  </span>
                </th>
                <td className="td break-all">{record.to}</td>
                <td className="td text-slate-soft">{humanise(record.kind)}</td>
                <td className="td">
                  <span className="font-mono text-xs">{record.reference}</span>
                </td>
                <td className="td">
                  {record.delivered ? (
                    <StatusPill status="AVAILABLE" label="Arrived" />
                  ) : (
                    <div className="min-w-[10rem]">
                      <StatusPill status="OVERDUE" label="Did not arrive" />
                      <span className="mt-xs block text-xs text-status-overdue">
                        The mailbox rejected it. Check the address, then try again.
                      </span>
                    </div>
                  )}
                </td>
                <td className="td">
                  <button
                    type="button"
                    disabled={sending}
                    onClick={() => onResend(record)}
                    className={
                      record.delivered ? 'btn-secondary px-md' : 'btn-primary px-md'
                    }
                  >
                    {sending ? (
                      <Loader2
                        className="h-4 w-4 shrink-0 animate-spin"
                        aria-hidden="true"
                      />
                    ) : (
                      <Send className="h-4 w-4 shrink-0" aria-hidden="true" />
                    )}
                    {sending
                      ? 'Sending'
                      : record.delivered
                        ? 'Send it again'
                        : 'Try sending it again'}
                  </button>
                </td>
              </tr>
            )
          })}
        </DataTable>
      )}
    </>
  )
}
