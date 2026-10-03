/**
 * The damage report reads, as cached queries, and what a damage write tells
 * the cache.
 *
 * The reports of a unit start with the damage segment, which query-client.ts
 * treats as never fresh, so a cached list is always asked for again when a
 * screen uses it.
 *
 * The writes are not here. A screen calls the functions in damage-reports.ts
 * for those, one request for each press of a button, and then hands the answer
 * to `rememberDamageReport`.
 */

import { queryOptions } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import type { DamageReport, DamageReportPage } from './contract'
import { DAMAGE_REPORT_PAGE_SIZE, listDamageReports } from './damage-reports'
import { ASSETS_KEY, COUNTER_KEY, DAMAGE_KEY, RENTALS_KEY } from './query-client'
import { rentalQueries } from './rental-queries'

const UNIT_SEGMENT = 'unit'

/** Pages are counted from one. A unit has few reports, so the screen reads the
 *  first page and says when there are more. */
const FIRST_PAGE = 1

export const damageQueries = {
  /** The newest reports filed against one unit, by its tag. */
  forUnit: (assetTag: string) =>
    queryOptions({
      queryKey: [DAMAGE_KEY, UNIT_SEGMENT, assetTag],
      queryFn: ({ signal }) =>
        listDamageReports({ assetTag, page: FIRST_PAGE, pageSize: DAMAGE_REPORT_PAGE_SIZE }, signal),
    }),
}

/**
 * Put a report a write answered with into every list that shows it, and mark
 * everything the write changed as out of date.
 *
 * A list that holds the report shows the server's answer at once, and every
 * list of reports is asked for again, because a new report changes which
 * reports a page holds and only the server knows its order.
 *
 * A report moves the unit into quarantine, to the workshop or back on the
 * shelf, so the locator and the counter's day are asked for again too. Filing
 * a report against a hire raises a charge on it and may settle its deposit, so
 * that hire is dropped from the cache altogether. The return screen then reads
 * it afresh when the assistant goes back to it, and never shows the deposit
 * still waiting while it does. The lists of hires are marked out of date as
 * well.
 */
export function rememberDamageReport(client: QueryClient, report: DamageReport): void {
  client.setQueriesData<DamageReportPage>({ queryKey: [DAMAGE_KEY, UNIT_SEGMENT] }, (page) =>
    page === undefined
      ? page
      : { ...page, items: page.items.map((shown) => (shown.id === report.id ? report : shown)) },
  )
  void client.invalidateQueries({ queryKey: [DAMAGE_KEY] })
  void client.invalidateQueries({ queryKey: [ASSETS_KEY] })
  void client.invalidateQueries({ queryKey: [COUNTER_KEY] })
  for (const key of [report.rentalId, report.rentalReference]) {
    if (key !== null) client.removeQueries({ queryKey: rentalQueries.detail(key).queryKey })
  }
  void client.invalidateQueries({ queryKey: [RENTALS_KEY] })
}

/** Mark the reports of every unit as out of date, so the screen showing them
 *  reads them again. A refusal that says a report moved on calls this. */
export function forgetDamageReports(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: [DAMAGE_KEY] })
}
