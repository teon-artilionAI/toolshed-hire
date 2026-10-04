/**
 * The chart on SC-22. The utilisation of each row on the page shown.
 *
 * It used to sit on SC-19 and draw a utilisation the prototype worked out for
 * each branch. The server now works utilisation out, for the rows of the
 * report, so the chart moved here and draws those rows, in the order the
 * server sent them, one bar each. It is still drawn without a charting
 * library, as one small SVG bar per row, because a single figure does not
 * earn a dependency.
 *
 * It is a magnitude comparison of one measure, so there is a single series,
 * no legend, and no hue that carries meaning. The percentage is printed beside
 * every bar, and a row with no serviceable days says so in words and has no
 * bar at all. The bar is drawn from the server's percentage as it arrived and
 * is never a figure of its own.
 *
 * The drawing is hidden from assistive technology, and a sentence that reads
 * every row and its utilisation stands in for it. The same figures are in the
 * table above, so nothing is only in the picture.
 */

import type { Percent, ReportGrouping, ReportRow } from '../../shared/api/contract'
import { percent } from '../../shared/format'
import { GROUPING_LABEL, utilisationWords } from './report-labels'

/** The width of the track, so a bar is as long as its percentage. */
const FULL_TRACK = 100
const BAR_HEIGHT = 4

/** How long a bar is, from the percentage the server sent. */
function barLength(rate: Percent | null): number {
  if (rate === null) return 0
  return Math.min(Math.max(Number(rate), 0), FULL_TRACK)
}

/** One row read out, for the sentence that stands in for the drawing. */
function spoken(row: ReportRow): string {
  return `${row.label}, ${row.utilisationPercent === null ? 'no serviceable days' : `${percent(row.utilisationPercent)} utilised`}`
}

export default function UtilisationChart({
  rows,
  groupBy,
}: {
  rows: readonly ReportRow[]
  groupBy: ReportGrouping
}) {
  const level = GROUPING_LABEL[groupBy].toLowerCase()
  return (
    <figure className="card mt-lg p-lg" aria-labelledby="utilisation-chart-caption">
      <figcaption id="utilisation-chart-caption" className="mb-md text-sm font-semibold text-ink">
        Utilisation of each {level} on this page, in the order of the table
      </figcaption>
      <p className="sr-only">{rows.map(spoken).join('. ')}.</p>
      <ul aria-hidden="true" className="flex flex-col gap-sm">
        {rows.map((row) => (
          <li key={row.key}>
            <div className="flex items-baseline justify-between gap-md text-sm">
              <span className={`min-w-0 break-words text-ink ${groupBy === 'asset' ? 'font-mono' : ''}`}>
                {row.label}
              </span>
              <span className="tabular shrink-0 font-semibold text-ink">
                {utilisationWords(row.utilisationPercent)}
              </span>
            </div>
            <svg
              viewBox={`0 0 ${FULL_TRACK} ${BAR_HEIGHT}`}
              preserveAspectRatio="none"
              className="mt-xs block h-2 w-full"
              focusable="false"
            >
              <rect x={0} y={0} width={FULL_TRACK} height={BAR_HEIGHT} rx={1} className="fill-muted" />
              <rect x={0} y={0} width={barLength(row.utilisationPercent)} height={BAR_HEIGHT} rx={1} className="fill-slate" />
            </svg>
          </li>
        ))}
      </ul>
    </figure>
  )
}
