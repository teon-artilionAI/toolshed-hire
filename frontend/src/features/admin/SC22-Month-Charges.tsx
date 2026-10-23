/**
 * The bookkeeper's month end charge file on SC-22 (B13.3).
 *
 * The owner picks a calendar month, and optionally the branch already chosen
 * on the report, and downloads every charge raised in it. The file includes
 * hire charges, late fees, damage recoveries and the three deposit movements,
 * with the totals at the end.
 */

import { useState } from 'react'
import { Download } from 'lucide-react'
import { downloadMonthlyCharges } from '../../shared/api/reporting'
import { ErrorState } from '../../shared/async-states'
import { saveFile } from '../../shared/save-file'
import { Card } from '../../shared/ui'

type State =
  | { step: 'waiting' }
  | { step: 'fetching' }
  | { step: 'saved'; fileName: string }
  | { step: 'failed'; error: unknown }

export function MonthCharges({
  month,
  branchCode,
  branchName,
  onMonth,
}: {
  month: string
  branchCode: string | null
  branchName: string
  onMonth: (month: string) => void
}) {
  const [state, setState] = useState<State>({ step: 'waiting' })

  async function download() {
    setState({ step: 'fetching' })
    try {
      const file = await downloadMonthlyCharges({
        month,
        ...(branchCode === null ? {} : { branchCode }),
      })
      saveFile(file)
      setState({ step: 'saved', fileName: file.fileName })
    } catch (error) {
      setState({ step: 'failed', error })
    }
  }

  return (
    <Card title="Month end charges">
      <p className="text-sm text-slate-soft">
        Every charge raised in a calendar month at {branchName}, deposits included, with the
        totals at the end. The bookkeeper uses this file to reconcile the month.
      </p>
      <div className="mt-md flex flex-wrap items-end gap-sm">
        <label className="flex flex-col gap-xs text-sm">
          <span className="font-medium text-ink">Month</span>
          <input
            type="month"
            className="input"
            value={month}
            onChange={(event) => {
              setState({ step: 'waiting' })
              onMonth(event.target.value)
            }}
          />
        </label>
        <button
          type="button"
          className="btn-primary px-md"
          onClick={() => void download()}
          disabled={state.step === 'fetching' || month.length !== 7}
        >
          <Download className="h-4 w-4 shrink-0" aria-hidden="true" />
          Download the month's charges
        </button>
        <p role="status" className="text-sm text-slate-soft">
          {state.step === 'fetching'
            ? 'Preparing the file.'
            : state.step === 'saved'
              ? `Downloaded ${state.fileName}.`
              : 'The period is the calendar month, from its first day to its last.'}
        </p>
      </div>
      {state.step === 'failed' && (
        <ErrorState
          heading="We could not download the charges"
          error={state.error}
          onRetry={() => void download()}
        />
      )}
    </Card>
  )
}
