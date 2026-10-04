/**
 * The "Download CSV" button of SC-22.
 *
 * The CSV route needs the access token, and a plain link would go out without
 * it. So the button asks the client for the file, which sends the token the
 * way it sends it for every call and renews the session once if it has to,
 * and then hands the bytes to the browser under the name the server gave
 * them. The file is every row of the report for the period and the filters on
 * the screen, not only the page shown.
 *
 * One press is one request, and the button is disabled while it runs. What
 * happened is said in a polite status beside the button, and a failure is
 * said in the shared error state with the way to try again.
 */

import { useState } from 'react'
import { Download } from 'lucide-react'
import type { UtilisationCsvQuery } from '../../shared/api/contract'
import { downloadUtilisationCsv } from '../../shared/api/reporting'
import { ErrorState } from '../../shared/async-states'
import { saveFile } from '../../shared/save-file'

type DownloadStep =
  | { step: 'waiting' }
  | { step: 'fetching' }
  | { step: 'saved'; fileName: string }
  | { step: 'failed'; error: unknown }

function statusWords(state: DownloadStep): string {
  switch (state.step) {
    case 'fetching':
      return 'Preparing the file.'
    case 'saved':
      return `Downloaded ${state.fileName}.`
    case 'failed':
      return 'The file was not downloaded.'
    default:
      return 'Every row of the report, as a file a spreadsheet opens.'
  }
}

export default function ReportDownload({ query }: { query: UtilisationCsvQuery }) {
  const [state, setState] = useState<DownloadStep>({ step: 'waiting' })
  const asked = JSON.stringify(query)
  const [lastAsked, setLastAsked] = useState(asked)
  if (asked !== lastAsked) {
    // A file saved or refused for other filters says nothing about these, so
    // the line starts again. A file still on its way is saved when it lands,
    // because it was asked for, and its answer is not said against these.
    setLastAsked(asked)
    setState({ step: 'waiting' })
  }

  async function download() {
    setState({ step: 'fetching' })
    try {
      const file = await downloadUtilisationCsv(query)
      saveFile(file)
      setState((now) => (now.step === 'fetching' ? { step: 'saved', fileName: file.fileName } : now))
    } catch (error) {
      // The client has logged the failure with its path and request id. The
      // person is told here, with the reference to quote.
      setState((now) => (now.step === 'fetching' ? { step: 'failed', error } : now))
    }
  }

  return (
    <div className="flex flex-col gap-sm">
      <div className="flex flex-wrap items-center gap-sm">
        <button
          type="button"
          className="btn-primary px-md"
          onClick={() => void download()}
          disabled={state.step === 'fetching'}
        >
          <Download className="h-4 w-4 shrink-0" aria-hidden="true" />
          Download CSV
        </button>
        <p role="status" className="text-sm text-slate-soft">
          {statusWords(state)}
        </p>
      </div>
      {state.step === 'failed' && (
        <ErrorState heading="We could not download the CSV" error={state.error} onRetry={() => void download()} />
      )}
    </div>
  )
}
