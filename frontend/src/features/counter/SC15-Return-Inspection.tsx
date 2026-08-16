/**
 * SC-15 Return and Condition Inspection.
 *
 * This is where the money is settled, so every figure on it is shown as the
 * sum that produced it rather than as a total the customer has to take on
 * trust. The worked example carried through the Task 1 document is the
 * default: hire TSH-H-26-000098, asset TSH-DR-0042 back two days late at
 * R120.00 a day, R240.00 withheld from a R1,200.00 deposit and R960.00
 * released.
 *
 * The deposit cannot be released while a unit is still out, and the screen
 * says which unit and why rather than simply disabling a button.
 */

import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { assets, customers, productModels, rentals, TODAY } from '../../shared/fixtures'
import { daysOverdue, formatDate, formatDateTime, money } from '../../shared/format'
import { Card, Notice, PageHeader, StatTile, StatusPill } from '../../shared/ui'
import { CONDITION_LABEL } from './SC14-checkout-model'
import { SettlementSummary } from './SC15-SettlementSummary'
import { ItemInspection } from './SC15-ItemInspection'
import type { ReturnDraft, ReturnRow } from './SC15-return-model'

export default function ReturnAndConditionInspection() {
  const { rentalId } = useParams()
  const rental = rentals.find((r) => r.id === rentalId || r.reference === rentalId)

  if (!rental) {
    return (
      <>
        <PageHeader
          screenId="SC-15"
          title="Return and condition inspection"
          subtitle="We could not find that hire."
        />
        <Notice tone="error" title={`No hire matches "${rentalId ?? ''}"`}>
          Check the reference on the customer's paperwork, or open the overdue
          worklist and start the return from there.
        </Notice>
        <Link to="/counter/overdue" className="btn-primary mt-md px-md">
          Open the overdue worklist
        </Link>
      </>
    )
  }

  return <Inspection key={rental.id} rentalKey={rental.id} />
}

function Inspection({ rentalKey }: { rentalKey: string }) {
  const rental = rentals.find((r) => r.id === rentalKey)!
  const customerName =
    customers.find((c) => c.id === rental.customerId)?.name ?? 'the customer'
  const daysLate = daysOverdue(rental.dueBackOn)

  const rows = useMemo<ReturnRow[]>(
    () =>
      rental.items.map((item) => {
        const asset = assets.find((a) => a.id === item.assetId)
        const model = productModels.find((m) => m.id === asset?.productModelId)
        return {
          itemId: item.id,
          assetId: item.assetId,
          tag: asset?.tag ?? 'Tag missing',
          modelName: model?.name ?? 'Unknown model',
          manufacturer: model?.manufacturer ?? '',
          lateFeePerDay: model?.lateFeePerDay ?? 0,
          conditionOut: item.conditionOut,
          meterOut: item.meterOut,
          hasMeter: item.meterOut !== undefined,
          returnedAt: item.returnedAt,
          conditionIn: item.conditionIn,
        }
      }),
    [rental],
  )

  const outstanding = rows.filter((row) => !row.returnedAt)
  const [settled, setSettled] = useState(false)
  const [draft, setDraft] = useState<Record<string, ReturnDraft>>(() =>
    Object.fromEntries(
      outstanding.map((row) => [
        row.itemId,
        {
          received: false,
          conditionIn: row.conditionOut,
          meterIn: row.meterOut === undefined ? '' : String(row.meterOut),
          chargeDamage: false,
          damageCharge: '',
        },
      ]),
    ),
  )

  function patch(itemId: string, next: Partial<ReturnDraft>) {
    setDraft((current) => ({ ...current, [itemId]: { ...current[itemId], ...next } }))
  }

  const lateFeeLines = outstanding.map((row) => ({
    tag: row.tag,
    perDay: row.lateFeePerDay,
    total: daysLate * row.lateFeePerDay,
  }))
  const lateFeeTotal = lateFeeLines.reduce((sum, line) => sum + line.total, 0)
  const damageTotal = outstanding.reduce((sum, row) => {
    const entry = draft[row.itemId]
    if (!entry.chargeDamage) return sum
    const amount = Number.parseFloat(entry.damageCharge)
    return sum + (Number.isFinite(amount) && amount > 0 ? amount : 0)
  }, 0)
  const stillOut = outstanding.filter((row) => !draft[row.itemId].received)

  return (
    <>
      <PageHeader
        screenId="SC-15"
        title="Return and condition inspection"
        subtitle={`${rental.reference} for ${customerName}, collected ${formatDate(rental.collectedAt)}.`}
        actions={<StatusPill status={rental.status} />}
      />

      {daysLate > 0 && !settled && (
        <div className="mb-lg">
          <Notice
            tone="warn"
            title={`Back ${daysLate} ${daysLate === 1 ? 'day' : 'days'} late`}
          >
            Due back {formatDate(rental.dueBackOn)}, today is {formatDate(TODAY)}.
            Late fees have accrued and come off the deposit below.
          </Notice>
        </div>
      )}

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Due back" value={formatDate(rental.dueBackOn)} />
        <StatTile
          label="Days late"
          value={daysLate}
          tone={daysLate > 0 ? 'bad' : 'good'}
          hint={daysLate > 0 ? `Counted to ${formatDate(TODAY)}` : 'Back on time'}
        />
        <StatTile label="Deposit held" value={money(rental.depositHeld)} />
        <StatTile
          label="Units still out"
          value={stillOut.length}
          tone={stillOut.length > 0 ? 'warn' : 'good'}
          hint={`${rows.length} on this hire`}
        />
      </div>

      <Card title="Units coming back" className="mb-lg">
        <div className="flex flex-col gap-lg">
          {rows.map((row) =>
            row.returnedAt ? (
              <div key={row.itemId} className="rounded border border-line bg-muted p-md">
                <div className="flex flex-wrap items-center justify-between gap-sm">
                  <p className="font-mono text-sm font-medium text-ink">{row.tag}</p>
                  <StatusPill status="RETURNED" label="Already back" />
                </div>
                <p className="mt-xs text-sm text-slate-soft">
                  {row.manufacturer} {row.modelName}, in {formatDateTime(row.returnedAt)}
                  {row.conditionIn && ` at ${CONDITION_LABEL[row.conditionIn]}`}.
                </p>
              </div>
            ) : (
              <ItemInspection
                key={row.itemId}
                row={row}
                draft={draft[row.itemId]}
                onChange={(next) => patch(row.itemId, next)}
              />
            ),
          )}
        </div>
      </Card>

      <div className="grid items-start gap-lg lg:grid-cols-2">
        <Card title="How the late fee was worked out">
          {lateFeeTotal === 0 ? (
            <p className="text-sm text-slate-soft">
              Nothing is late on this hire, so there is no fee to explain.
            </p>
          ) : (
            <div className="flex flex-col gap-sm text-sm">
              <p className="text-slate-soft">
                Due back {formatDate(rental.dueBackOn)}. Today is {formatDate(TODAY)}.
                That is {daysLate} {daysLate === 1 ? 'day' : 'days'} late.
              </p>
              <ul className="flex flex-col gap-sm">
                {lateFeeLines.map((line) => (
                  <li
                    key={line.tag}
                    className="tabular rounded bg-muted p-sm font-mono text-sm text-ink"
                  >
                    {line.tag}: {daysLate} × {money(line.perDay)} = {money(line.total)}
                  </li>
                ))}
              </ul>
              <p className="tabular font-semibold text-ink">
                Late fee to withhold: {money(lateFeeTotal)}
              </p>
            </div>
          )}
        </Card>

        <SettlementSummary
          deposit={rental.depositHeld}
          lateFee={lateFeeTotal}
          damage={damageTotal}
          blockedBy={stillOut.map((row) => row.tag)}
          settled={settled}
          onSettle={() => setSettled(true)}
          customerName={customerName}
          reference={rental.reference}
        />
      </div>
    </>
  )
}

