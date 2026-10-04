/**
 * SC-22, Utilisation and Gross Contribution.
 *
 * This is the screen that answers the client's third pain point. Nobody can
 * say which units earn their keep. It reports days on hire against the days a
 * unit could be hired, and what each unit brought in less what its repairs
 * cost, for a period, at four levels of detail, and it hands every row over as
 * a CSV.
 *
 * It is called gross contribution and never profit. The system holds no
 * depreciation, no staff cost, no premises cost and no finance cost, so a
 * figure labelled profit would be a figure that is not true. The server sends
 * the two definitions with every answer and the screen shows them in full
 * beside the figures.
 *
 * Every figure is the server's, from `GET /api/admin/reports/utilisation`. The
 * browser works out no figure, keeps the rows in the order the server sent
 * them, and asks for one page at a time. The period, the grouping, the filters
 * and the page live in the address, read and written by report-address.ts, so
 * a reload or a shared link shows the same figures. An address that does not
 * name a period is written out with the last full month, so a link copied
 * from it names the period too.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { adminQueries } from '../../shared/api/admin-queries'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { fieldErrorsFromProblem, otherFieldMessages } from '../../shared/api/problem-fields'
import { todayInBranchTime } from '../../shared/today'
import { PageHeader } from '../../shared/ui'
import {
  FIRST_PAGE,
  REPORT_FIELDS,
  addressSays,
  readReportFilters,
  reportQueryFor,
  writeReportFilters,
} from './report-address'
import type { ReportFilters as Filters } from './report-address'
import ReportFilters from './ReportFilters'
import ReportResults from './ReportResults'

export default function UtilisationReport() {
  const [params, setParams] = useSearchParams()
  const [today] = useState(() => todayInBranchTime())
  const filters = useMemo(() => readReportFilters(params, today), [params, today])

  // The address is written out in full whenever it does not already say what
  // the report shows, in place of the entry and not as a new one.
  useEffect(() => {
    if (!addressSays(params, filters)) setParams(writeReportFilters(filters), { replace: true })
  }, [params, filters, setParams])

  const update = useCallback(
    (changes: Partial<Filters>) => {
      // Any change to what is reported starts again from the first page.
      setParams(writeReportFilters({ ...filters, page: FIRST_PAGE, ...changes }), { replace: true })
    },
    [filters, setParams],
  )

  const branches = useQuery(catalogueQueries.branches())
  const categories = useQuery(catalogueQueries.categories())
  const report = useQuery(adminQueries.report(reportQueryFor(filters)))
  const fieldErrors = fieldErrorsFromProblem(report.error)

  return (
    <>
      <PageHeader
        screenId="SC-22"
        title="Utilisation and gross contribution"
        subtitle="How hard the fleet worked over a period, and what it brought in less what its repairs cost. These figures are gross contribution and not profit."
      />
      <ReportFilters
        filters={filters}
        fieldErrors={fieldErrors}
        branches={branches}
        categories={categories}
        onChange={update}
      />
      <ReportResults
        report={report}
        filters={filters}
        otherMessages={otherFieldMessages(fieldErrors, REPORT_FIELDS)}
        onPage={(page) => update({ page })}
        onClearFilters={() => update({ branchCode: null, categorySlug: null })}
      />
    </>
  )
}
