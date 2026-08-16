/**
 * SC-18 Overdue and Late Fee Worklist.
 *
 * The morning job. Every hire that is past its due date, what it has cost the
 * customer so far, and how long is left before it has to be escalated.
 *
 * Fees are shown as the sum that produced them, days late times the daily
 * rate for that model, because a counter assistant reads that figure out over
 * the phone and has to be able to defend it. Escalation happens at fourteen
 * days and every row carries its countdown, so the rule is visible even when
 * nothing has reached it yet.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { PhoneCall, PhoneOff } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import type { BranchCode } from '../../shared/types'
import { formatDate, money } from '../../shared/format'
import {
  Card,
  DataTable,
  EmptyState,
  PageHeader,
  StatTile,
  StatusPill,
} from '../../shared/ui'
import { UnlinkedUnits } from './SC18-UnlinkedUnits'
import type { AgeFilter } from './SC18-overdue-data'
import { ESCALATION_DAYS, OVERDUE_ROWS, matchesAge } from './SC18-overdue-data'

type BranchFilter = 'ALL' | BranchCode

const AGE_FILTERS: { value: AgeFilter; label: string }[] = [
  { value: 'ALL', label: 'Any age' },
  { value: 'FRESH', label: 'One to three days late' },
  { value: 'CHASING', label: 'Four to thirteen days late' },
  { value: 'ESCALATED', label: 'Fourteen days or more' },
]

const BRANCH_OPTIONS: { code: BranchFilter; name: string }[] = [
  { code: 'ALL', name: 'All three branches' },
  ...branches.map((branch) => ({ code: branch.code as BranchFilter, name: branch.name })),
]

export default function OverdueAndLateFeeWorklist() {
  const [branchFilter, setBranchFilter] = useState<BranchFilter>('ALL')
  const [ageFilter, setAgeFilter] = useState<AgeFilter>('ALL')
  const [chased, setChased] = useState<Record<string, boolean>>({})

  const rows = useMemo(
    () =>
      OVERDUE_ROWS.filter(
        (row) =>
          (branchFilter === 'ALL' || row.branchCode === branchFilter) &&
          matchesAge(row, ageFilter),
      ),
    [branchFilter, ageFilter],
  )

  const escalated = OVERDUE_ROWS.filter((row) => row.daysLate >= ESCALATION_DAYS)
  const unitsOut = rows.reduce((sum, row) => sum + row.units.length, 0)
  const feesToDate = rows.reduce((sum, row) => sum + row.feeToDate, 0)
  const accruingDaily = rows.reduce((sum, row) => sum + row.feePerDay, 0)

  return (
    <>
      <PageHeader
        screenId="SC-18"
        title="Overdue and late fees"
        subtitle="Everything past its due date, what it has cost so far, and how long before it goes to the owner for recovery."
      />

      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Hires overdue"
          value={rows.length}
          tone={rows.length > 0 ? 'bad' : 'good'}
        />
        <StatTile label="Units still out" value={unitsOut} hint="Not back on a shelf" />
        <StatTile
          label="Fees accrued"
          value={money(feesToDate)}
          tone={feesToDate > 0 ? 'warn' : 'default'}
          hint={`Growing by ${money(accruingDaily)} a day`}
        />
        <StatTile
          label="At escalation"
          value={escalated.length}
          tone={escalated.length > 0 ? 'bad' : 'good'}
          hint={`${ESCALATION_DAYS} days late or more`}
        />
      </div>

      <Card className="mb-lg">
        <div className="flex flex-col gap-md">
          <fieldset className="min-w-0">
            <legend className="field-label">Branch</legend>
            <div className="mt-xs flex flex-wrap gap-sm">
              {BRANCH_OPTIONS.map((option) => {
                const active = branchFilter === option.code
                return (
                  <button
                    key={option.code}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setBranchFilter(option.code)}
                    className={`btn px-md ${
                      active
                        ? 'bg-accent font-semibold text-accent-ink'
                        : 'border border-line bg-surface text-ink hover:bg-muted'
                    }`}
                  >
                    {option.name}
                  </button>
                )
              })}
            </div>
          </fieldset>
          <div className="max-w-sm">
            <label className="field-label" htmlFor="overdue-age">
              How late
            </label>
            <select
              id="overdue-age"
              className="field-input cursor-pointer"
              value={ageFilter}
              onChange={(e) => setAgeFilter(e.target.value as AgeFilter)}
            >
              {AGE_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      <p aria-live="polite" className="sr-only">
        {rows.length} overdue {rows.length === 1 ? 'hire' : 'hires'} listed
      </p>

      <div className="mb-lg">
        {rows.length === 0 ? (
          <div className="card">
            <EmptyState
              title="Nothing is overdue here"
              body="No hire at this branch matches that age. Widen the filters to see the rest of the fleet, or come back after the morning collections."
            />
          </div>
        ) : (
          <DataTable
            caption="Overdue hires with the late fee accrued against each"
            columns={[
              'Hire',
              'Customer',
              'Units out',
              'Due back',
              'Late fee to date',
              'Escalation',
              'Next step',
            ]}
          >
            {rows.map((row) => (
              <tr key={row.rentalId} className="transition-colors duration-200 hover:bg-muted">
                <th scope="row" className="td whitespace-nowrap font-mono font-medium text-ink">
                  {row.reference}
                  <span className="mt-xs block font-sans text-xs font-normal text-slate-soft">
                    {row.branchName}
                  </span>
                </th>
                <td className="td text-ink">
                  {row.customerName}
                  <span className="tabular mt-xs block text-xs text-slate-soft">
                    {row.customerPhone}
                  </span>
                </td>
                <td className="td">
                  <ul className="flex flex-col gap-xs">
                    {row.units.map((unit) => (
                      <li key={unit.tag} className="font-mono text-xs text-ink">
                        {unit.tag}
                      </li>
                    ))}
                  </ul>
                </td>
                <td className="td whitespace-nowrap">
                  <span className="text-ink">{formatDate(row.dueBackOn)}</span>
                  <span className="mt-xs block">
                    <StatusPill
                      status="OVERDUE"
                      label={`${row.daysLate} ${row.daysLate === 1 ? 'day' : 'days'} late`}
                    />
                  </span>
                </td>
                <td className="td whitespace-nowrap">
                  <span className="tabular block font-mono text-xs text-slate-soft">
                    {row.daysLate} × {money(row.feePerDay)}
                  </span>
                  <span className="tabular block font-semibold text-ink">
                    {money(row.feeToDate)}
                  </span>
                </td>
                <td className="td whitespace-nowrap text-slate-soft">
                  {row.daysToEscalation > 0
                    ? `In ${row.daysToEscalation} days`
                    : 'Escalated to the owner'}
                </td>
                <td className="td">
                  <div className="flex flex-wrap gap-sm">
                    <button
                      type="button"
                      className={`btn whitespace-nowrap px-md ${
                        chased[row.rentalId]
                          ? 'border border-line bg-muted text-slate-soft'
                          : 'border border-line bg-surface text-ink hover:bg-muted'
                      }`}
                      onClick={() =>
                        setChased((current) => ({
                          ...current,
                          [row.rentalId]: !current[row.rentalId],
                        }))
                      }
                    >
                      {chased[row.rentalId] ? (
                        <PhoneOff className="h-4 w-4 shrink-0" aria-hidden="true" />
                      ) : (
                        <PhoneCall className="h-4 w-4 shrink-0" aria-hidden="true" />
                      )}
                      {chased[row.rentalId] ? 'Rung today' : 'Ring the customer'}
                    </button>
                    <Link
                      to={`/counter/return/${row.rentalId}`}
                      className="btn-primary whitespace-nowrap px-md"
                    >
                      Take the return
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </div>

      <div className="mb-lg">
        <Card title={`Escalation queue, ${ESCALATION_DAYS} days and over`}>
          {escalated.length === 0 ? (
            <EmptyState
              title="Nothing has reached escalation"
              body={`A hire goes to the owner for formal recovery once it is ${ESCALATION_DAYS} days late. The longest running hire is ${OVERDUE_ROWS[0]?.daysLate ?? 0} days late, so nothing qualifies yet. Keep ringing the hires above and it stays that way.`}
            />
          ) : (
            <ul className="flex flex-col gap-sm">
              {escalated.map((row) => (
                <li
                  key={row.rentalId}
                  className="flex flex-wrap items-center justify-between gap-sm rounded border border-line p-md"
                >
                  <div className="min-w-0">
                    <p className="font-mono text-sm font-medium text-ink">{row.reference}</p>
                    <p className="text-sm text-slate-soft">
                      {row.customerName}, {row.daysLate} days late,{' '}
                      {money(row.feeToDate)} accrued
                    </p>
                  </div>
                  <Link to={`/counter/return/${row.rentalId}`} className="btn-secondary px-md">
                    Open the hire
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <UnlinkedUnits branchFilter={branchFilter} />
    </>
  )
}
