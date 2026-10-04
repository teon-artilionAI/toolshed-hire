/**
 * The words the owner's screens use for the reporting figures.
 *
 * The figures themselves are the server's, written as they arrive. Only the
 * words around them are chosen here, so every screen says "gross
 * contribution" the same way and never anything that could be read as profit.
 */

import type { IsoDate, Percent, ReportGrouping } from '../../shared/api/contract'
import { formatDate, percent } from '../../shared/format'

/** What each grouping is called in the menu that chooses it, and what the
 *  first column of the table is headed at it. */
export const GROUPING_LABEL: Record<ReportGrouping, string> = {
  asset: 'Unit',
  model: 'Model',
  category: 'Category',
  branch: 'Branch',
}

/** How the report names its rows in a sentence, for example "by model". */
export const GROUPING_PHRASE: Record<ReportGrouping, string> = {
  asset: 'by unit',
  model: 'by model',
  category: 'by category',
  branch: 'by branch',
}

/** What a utilisation over no serviceable days reads as. */
export const NO_SERVICEABLE_DAYS = 'No serviceable days'

/** The name of the figure, the same on every screen. */
export const GROSS_CONTRIBUTION = 'Gross contribution'

/**
 * A utilisation the server sent, as a percentage, or the words for one over
 * no serviceable days, which the server sends as null.
 */
export function utilisationWords(rate: Percent | null): string {
  return rate === null ? NO_SERVICEABLE_DAYS : percent(rate)
}

/**
 * A period the way the API counts it, `[from, to)`, in words. The second day
 * is said to be left out, because that is what the server did with it.
 */
export function periodWords(from: IsoDate, to: IsoDate): string {
  return `${formatDate(from)} up to but not including ${formatDate(to)}`
}
