/**
 * SC-13 New Booking and Asset Allocation.
 *
 * A booking is a customer, a period, and a list of tools with a real unit
 * behind each one. The screen refuses to pretend: if the unit the customer
 * asked for is already spoken for, it says which booking has it and offers
 * another unit, another branch or different dates rather than a shrug.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarPlus, Plus } from 'lucide-react'
import { Card, EmptyState, Field, Notice, PageHeader, StatusPill } from '../../shared/ui'
import { useSession } from '../../shared/session'
import { TODAY, branches, customers, productModels } from '../../shared/fixtures'
import { daysBetween, money } from '../../shared/format'
import type { BranchCode } from '../../shared/types'
import { addDays, modelById } from './counter-desk-data'
import type { BookingLineDraft } from './counter-availability'
import { allocateLine, nextReservationReference } from './counter-availability'
import LineEditor from './SC13-Line-Editor'
import BookingConfirmed from './SC13-Booking-Confirmed'

const DEFAULT_HIRE_DAYS = 4

function newLine(): BookingLineDraft {
  return {
    id: `line-${Date.now()}`,
    modelId: productModels[0].id,
    quantity: 1,
    mode: 'AUTO',
    assetIds: [],
  }
}

export default function NewBooking() {
  const { branch } = useSession()
  const [customerId, setCustomerId] = useState('')
  const [branchCode, setBranchCode] = useState<BranchCode>(branch.code)
  const [startDate, setStartDate] = useState(TODAY)
  const [endDate, setEndDate] = useState(addDays(TODAY, DEFAULT_HIRE_DAYS))
  const [lines, setLines] = useState<BookingLineDraft[]>([newLine()])
  const [showBlockers, setShowBlockers] = useState(false)
  const [reference, setReference] = useState<string | null>(null)

  const customer = customers.find((c) => c.id === customerId)
  const days = Math.max(1, daysBetween(startDate, endDate))

  const allocations = useMemo(
    () => lines.map((line) => allocateLine(line, branchCode, startDate, endDate)),
    [lines, branchCode, startDate, endDate],
  )

  const hireTotal = lines.reduce(
    (sum, line) => sum + modelById(line.modelId).dailyRate * days * line.quantity,
    0,
  )
  const depositTotal = lines.reduce(
    (sum, line) => sum + modelById(line.modelId).depositAmount * line.quantity,
    0,
  )

  const blockers: string[] = []
  if (!customer) blockers.push('Choose the customer this hire is for.')
  if (customer?.onHold) {
    blockers.push(
      `${customer.name} has an account on hold, so no new hire can go out. An owner has to lift the hold first.`,
    )
  }
  if (startDate < TODAY) blockers.push('The collection date cannot be in the past.')
  if (endDate <= startDate) blockers.push('The return date has to be after the collection date.')
  if (lines.length === 0) blockers.push('Add at least one tool to the booking.')
  allocations.forEach((allocation, index) => {
    if (allocation.problem) {
      blockers.push(`Tool ${index + 1}, ${modelById(lines[index].modelId).name}: ${allocation.problem}`)
    }
  })

  function updateLine(index: number, next: BookingLineDraft) {
    setLines((current) => current.map((line, i) => (i === index ? next : line)))
  }

  function confirm() {
    if (blockers.length > 0) {
      setShowBlockers(true)
      window.scrollTo({ top: 0 })
      return
    }
    setReference(nextReservationReference())
    window.scrollTo({ top: 0 })
  }

  if (reference && customer) {
    return (
      <BookingConfirmed
        reference={reference}
        customer={customer}
        branchCode={branchCode}
        startDate={startDate}
        endDate={endDate}
        lines={lines}
        allocations={allocations}
        hireTotal={hireTotal}
        depositTotal={depositTotal}
        onStartAnother={() => {
          setReference(null)
          setLines([newLine()])
          setCustomerId('')
          setShowBlockers(false)
        }}
      />
    )
  }

  return (
    <div>
      <PageHeader
        screenId="SC-13"
        title="New booking"
        subtitle="Pick the customer and the dates, then add the tools. Units are set aside as you go."
      />

      {showBlockers && blockers.length > 0 && (
        <div className="mb-lg">
          <Notice tone="error" title="This booking cannot be made yet">
            <ul className="ml-md list-disc">
              {blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </Notice>
        </div>
      )}

      <Card title="Who and when" className="mb-lg">
        <div className="grid gap-md md:grid-cols-2 xl:grid-cols-4">
          <Field
            label="Customer"
            htmlFor="booking-customer"
            help="Not on file yet? Register them first."
          >
            <select
              id="booking-customer"
              className="field-input cursor-pointer"
              value={customerId}
              onChange={(event) => setCustomerId(event.target.value)}
            >
              <option value="">Choose a customer</option>
              {customers.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                  {option.onHold ? ' (account on hold)' : ''}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Collecting from" htmlFor="booking-branch">
            <select
              id="booking-branch"
              className="field-input cursor-pointer"
              value={branchCode}
              onChange={(event) => setBranchCode(event.target.value as BranchCode)}
            >
              {branches.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.name}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Goes out" htmlFor="booking-start">
            <input
              id="booking-start"
              type="date"
              className="field-input tabular cursor-pointer"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </Field>

          <Field
            label="Back by"
            htmlFor="booking-end"
            help={`${days} ${days === 1 ? 'day' : 'days'} on hire.`}
          >
            <input
              id="booking-end"
              type="date"
              className="field-input tabular cursor-pointer"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </Field>
        </div>

        {customer && (
          <div className="mt-md flex flex-wrap items-center gap-sm">
            <span className="text-sm text-slate-soft">
              {customer.phone}, {customer.billingSuburb}
            </span>
            {customer.onHold ? (
              <StatusPill status="OVERDUE" label="Account on hold" />
            ) : (
              <StatusPill status="AVAILABLE" label="Good standing" />
            )}
            <Link to="/counter/customers" className="btn-ghost px-sm text-sm">
              Find someone else
            </Link>
          </div>
        )}
      </Card>

      <div className="mb-lg">
        {lines.length === 0 ? (
          <Card title="Tools on this booking">
            <EmptyState
              title="No tools on this booking yet"
              body="Add the first tool and the system will set a unit aside for the dates above."
              action={
                <button type="button" onClick={() => setLines([newLine()])} className="btn-primary">
                  Add a tool
                </button>
              }
            />
          </Card>
        ) : (
          <ul className="flex flex-col gap-md">
            {lines.map((line, index) => (
              <LineEditor
                key={line.id}
                line={line}
                position={index + 1}
                branch={branchCode}
                startDate={startDate}
                endDate={endDate}
                allocation={allocations[index]}
                onChange={(next) => updateLine(index, next)}
                onRemove={() => setLines((current) => current.filter((_, i) => i !== index))}
                onMoveBranch={(code) => setBranchCode(code)}
                onShiftPeriod={(start, end) => {
                  setStartDate(start)
                  setEndDate(end)
                }}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="mb-lg">
        <button
          type="button"
          onClick={() => setLines((current) => [...current, newLine()])}
          className="btn-secondary"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add another tool
        </button>
      </div>

      <Card title="What it comes to">
        <dl className="tabular grid gap-sm sm:grid-cols-3">
          <div>
            <dt className="text-sm text-slate-soft">Hire, {days} {days === 1 ? 'day' : 'days'}</dt>
            <dd className="text-xl font-semibold text-ink">{money(hireTotal)}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-soft">Deposit held</dt>
            <dd className="text-xl font-semibold text-ink">{money(depositTotal)}</dd>
          </div>
          <div>
            <dt className="text-sm text-slate-soft">Taken on collection</dt>
            <dd className="text-xl font-semibold text-ink">{money(hireTotal + depositTotal)}</dd>
          </div>
        </dl>
        <p className="mt-md text-sm text-slate-soft">
          The deposit is refundable. Anything back late carries the model late fee for each day.
        </p>
        <button type="button" onClick={confirm} className="btn-primary mt-lg">
          <CalendarPlus className="h-4 w-4" aria-hidden="true" />
          Confirm the booking
        </button>
      </Card>
    </div>
  )
}
