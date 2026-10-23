/**
 * The statement and data export actions on SC-09.
 *
 * The customer chooses a period, reads the statement the ledger holds for it,
 * and can download the same rows as a CSV file, print what is on screen, or
 * download everything held about them as JSON. The figures are the server's:
 * every deposit movement and every charge is a row the API sent.
 *
 * The card has the shared loading, failed and empty states. A refusal names
 * the bound that was wrong when the server says which one it was, and every
 * file is saved under the name the server gave it. The print action uses the
 * browser's own print dialogue, and the controls are left out of the printout.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download, Printer } from 'lucide-react'
import { queryPhase } from '../../shared/api/query-phase'
import { ACCOUNT_KEY } from '../../shared/api/query-client'
import {
  downloadMyData,
  downloadMyStatementCsv,
  getMyStatement,
} from '../../shared/api/statement'
import type { MyStatement } from '../../shared/api/contract'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { formatDate, money } from '../../shared/format'
import { saveFile } from '../../shared/save-file'
import { Card, EmptyState, Notice } from '../../shared/ui'

type DownloadState =
  | { step: 'waiting' }
  | { step: 'fetching'; what: 'statement' | 'data' }
  | { step: 'saved'; fileName: string }
  | { step: 'failed'; what: 'statement' | 'data'; error: unknown }

const ONE_DAY_MS = 24 * 60 * 60 * 1000
const STATEMENT_QUERY_SEGMENT = 'statement'

function isoDay(day: Date): string {
  return day.toISOString().slice(0, 10)
}

function firstDayOfYear(): string {
  const today = new Date()
  return `${today.getUTCFullYear()}-01-01`
}

function tomorrow(): string {
  return isoDay(new Date(Date.now() + ONE_DAY_MS))
}

export function AccountStatement() {
  const [from, setFrom] = useState(firstDayOfYear)
  const [to, setTo] = useState(tomorrow)
  const [applied, setApplied] = useState({ from, to })
  const [download, setDownload] = useState<DownloadState>({ step: 'waiting' })
  const statement = useQuery({
    queryKey: [ACCOUNT_KEY, STATEMENT_QUERY_SEGMENT, applied.from, applied.to],
    queryFn: ({ signal }) => getMyStatement({ from: applied.from, to: applied.to }, signal),
  })
  const phase = queryPhase(statement)
  const data = statement.data

  function applyPeriod() {
    setDownload({ step: 'waiting' })
    setApplied({ from, to })
  }

  async function saveStatement() {
    setDownload({ step: 'fetching', what: 'statement' })
    try {
      const file = await downloadMyStatementCsv(applied)
      saveFile(file)
      setDownload((now) =>
        now.step === 'fetching' ? { step: 'saved', fileName: file.fileName } : now,
      )
    } catch (error) {
      setDownload((now) =>
        now.step === 'fetching' ? { step: 'failed', what: 'statement', error } : now,
      )
    }
  }

  async function saveEverything() {
    setDownload({ step: 'fetching', what: 'data' })
    try {
      const file = await downloadMyData()
      saveFile(file)
      setDownload((now) =>
        now.step === 'fetching' ? { step: 'saved', fileName: file.fileName } : now,
      )
    } catch (error) {
      setDownload((now) =>
        now.step === 'fetching' ? { step: 'failed', what: 'data', error } : now,
      )
    }
  }

  return (
    <Card title="Statement and your data">
      <div className="flex flex-col gap-md">
        <p className="text-sm text-slate-soft">
          A statement lists your hires, their charges and where each deposit stands. It is read
          from the records the branch already holds. You can download it, print it, or download
          everything held about you.
        </p>

        <form
          className="flex flex-wrap items-end gap-sm print:hidden"
          onSubmit={(event) => {
            event.preventDefault()
            applyPeriod()
          }}
        >
          <label className="flex flex-col gap-xs text-sm">
            <span className="font-medium text-ink">From</span>
            <input
              type="date"
              className="input"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-xs text-sm">
            <span className="font-medium text-ink">To</span>
            <input
              type="date"
              className="input"
              value={to}
              onChange={(event) => setTo(event.target.value)}
            />
          </label>
          <button type="submit" className="btn-secondary px-md">
            Read this period
          </button>
        </form>

        <div className="flex flex-wrap items-center gap-sm print:hidden">
          <button
            type="button"
            className="btn-primary px-md"
            onClick={() => void saveStatement()}
            disabled={download.step === 'fetching'}
          >
            <Download className="h-4 w-4 shrink-0" aria-hidden="true" />
            Download my statement
          </button>
          <button
            type="button"
            className="btn-secondary px-md"
            onClick={() => void saveEverything()}
            disabled={download.step === 'fetching'}
          >
            <Download className="h-4 w-4 shrink-0" aria-hidden="true" />
            Download all my data
          </button>
          <button
            type="button"
            className="btn-ghost px-md"
            onClick={() => window.print()}
            disabled={phase !== 'ready'}
          >
            <Printer className="h-4 w-4 shrink-0" aria-hidden="true" />
            Print this statement
          </button>
          <p role="status" className="text-sm text-slate-soft">
            {download.step === 'fetching'
              ? download.what === 'statement'
                ? 'Preparing your statement.'
                : 'Preparing your data.'
              : download.step === 'saved'
                ? `Downloaded ${download.fileName}.`
                : download.step === 'failed'
                  ? 'The file was not downloaded.'
                  : 'The statement covers the period above. Dates are half open, so a hire returned on the closing date is in the next period.'}
          </p>
        </div>

        {download.step === 'failed' && (
          <ErrorState
            heading={
              download.what === 'statement'
                ? 'We could not download your statement'
                : 'We could not download your data'
            }
            error={download.error}
            onRetry={() =>
              download.what === 'statement' ? void saveStatement() : void saveEverything()
            }
          />
        )}

        {phase === 'loading' && <LoadingState shape="rows" count={3} />}
        {phase === 'failed' && (
          <ErrorState
            what="your statement"
            error={statement.error}
            onRetry={() => void statement.refetch()}
          />
        )}
        {phase === 'ready' && data && <StatementBody statement={data} />}
      </div>
    </Card>
  )
}

function StatementBody({ statement }: { statement: MyStatement }) {
  if (statement.items.length === 0) {
    return (
      <EmptyState
        title="Nothing in this period"
        body="No hire went out, came back or had a charge raised between these dates. Try a wider period."
      />
    )
  }
  return (
    <section className="flex flex-col gap-md" aria-label="Your statement">
      <dl className="grid gap-sm sm:grid-cols-2 lg:grid-cols-4">
        <Figure term="Hires" value={String(statement.totals.hireCount)} />
        <Figure term="Charges with VAT" value={money(statement.totals.chargesTotalIncVat)} />
        <Figure term="Deposits held" value={money(statement.totals.depositHeld)} />
        <Figure term="Balance due" value={money(statement.totals.balanceDue)} />
      </dl>
      <p className="text-sm text-slate-soft">
        {formatDate(statement.from)} up to but not including {formatDate(statement.to)}. The
        statement was read on {formatDate(statement.generatedAt.slice(0, 10))}.
      </p>
      <ol className="flex flex-col gap-md" aria-label="Hires on the statement">
        {statement.items.map((line) => (
          <li key={line.rentalId} className="rounded-md border border-line p-md">
            <div className="flex flex-wrap items-baseline justify-between gap-sm">
              <h3 className="font-semibold text-ink">{line.reference}</h3>
              <span className="text-sm text-slate-soft">{line.status.replaceAll('_', ' ')}</span>
            </div>
            <p className="mt-xs text-sm text-slate-soft">
              {line.branchName} ({line.branchCode}), {formatDate(line.from)} to{' '}
              {formatDate(line.dueBackOn)}
            </p>
            <dl className="mt-sm grid gap-sm sm:grid-cols-2">
              <Figure term="Deposit held" value={money(line.depositHeld)} />
              <Figure
                term="Deposit withheld and refunded"
                value={`${money(line.depositWithheld)} / ${money(line.depositRefunded)}`}
              />
              <Figure term="Balance due" value={money(line.balanceDue)} />
              <Figure term="Charges with VAT" value={money(line.chargesTotalIncVat)} />
            </dl>
            <h4 className="mt-sm text-sm font-semibold text-ink">Charges</h4>
            <ul className="mt-xs flex flex-col gap-xs">
              {line.charges.map((charge) => (
                <li key={charge.id} className="text-sm">
                  <span className="block text-ink">{charge.description}</span>
                  <span className="tabular block text-slate-soft">
                    {money(charge.amountIncVat)} with VAT, {charge.status.toLowerCase()}
                  </span>
                </li>
              ))}
              {line.charges.length === 0 && (
                <li className="text-sm text-slate-soft">No charges on this hire yet.</li>
              )}
            </ul>
          </li>
        ))}
      </ol>
      <Notice tone="info" title="Where the figures come from">
        <p>
          Every amount is a row the branch recorded: a charge raised, a deposit taken, withheld
          or given back. Nothing on this page is worked out again from a rate.
        </p>
      </Notice>
    </section>
  )
}

function Figure({ term, value }: { term: string; value: string }) {
  return (
    <div className="rounded-md border border-line p-sm">
      <dt className="text-sm text-slate-soft">{term}</dt>
      <dd className="tabular text-lg font-semibold text-ink">{value}</dd>
    </div>
  )
}
