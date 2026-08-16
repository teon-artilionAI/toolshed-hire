/**
 * The second list on SC-18: units the system believes are out, that no open
 * hire accounts for.
 *
 * This is not an overdue hire, so it does not belong in the fee table, but it
 * is the same job. A unit marked on hire with nobody's name against it is a
 * unit nobody can find, and that is the complaint the client actually made.
 * It is a reconciliation task for the counter, not a fee to chase.
 */

import { Link } from 'react-router-dom'
import { assets, branches, productModels, rentals } from '../../shared/fixtures'
import type { BranchCode } from '../../shared/types'
import { Card, DataTable, EmptyState, StatusPill } from '../../shared/ui'

interface UnlinkedUnit {
  id: string
  tag: string
  modelLabel: string
  branchCode: BranchCode
  branchName: string
}

/** On hire, but no open hire item points at it. */
const UNLINKED_UNITS: UnlinkedUnit[] = assets
  .filter(
    (asset) =>
      asset.status === 'ON_HIRE' &&
      !rentals.some((rental) =>
        rental.items.some((item) => item.assetId === asset.id && !item.returnedAt),
      ),
  )
  .map((asset) => {
    const model = productModels.find((m) => m.id === asset.productModelId)
    return {
      id: asset.id,
      tag: asset.tag,
      modelLabel: model ? `${model.manufacturer} ${model.name}` : 'Unknown model',
      branchCode: asset.branchCode,
      branchName: branches.find((b) => b.code === asset.branchCode)?.name ?? asset.branchCode,
    }
  })

export function UnlinkedUnits({ branchFilter }: { branchFilter: 'ALL' | BranchCode }) {
  const rows =
    branchFilter === 'ALL'
      ? UNLINKED_UNITS
      : UNLINKED_UNITS.filter((row) => row.branchCode === branchFilter)

  return (
    <Card title="Out, with no hire against them">
      <p className="mb-md text-sm text-slate-soft">
        These units are marked as out but no open hire accounts for them, so
        there is no customer to ring and no fee accruing. Somebody has taken
        them without the hire being opened. Ring the branch, find out who has
        them, and open a hire or bring them back onto the shelf.
      </p>

      {rows.length === 0 ? (
        <EmptyState
          title="Every unit out is accounted for"
          body="Each unit marked as on hire has an open hire with a customer's name on it. Nothing to reconcile at this branch."
        />
      ) : (
        <DataTable
          caption="Units marked as on hire with no open hire record"
          columns={['Tag', 'Model', 'Branch', 'State', 'Action']}
        >
          {rows.map((row) => (
            <tr key={row.id} className="transition-colors duration-200 hover:bg-muted">
              <th scope="row" className="td whitespace-nowrap font-mono font-medium text-ink">
                {row.tag}
              </th>
              <td className="td text-ink">{row.modelLabel}</td>
              <td className="td whitespace-nowrap text-slate-soft">{row.branchName}</td>
              <td className="td">
                <StatusPill status="ON_HIRE" label="Out, unaccounted" />
              </td>
              <td className="td">
                <Link
                  to={`/counter/damage/${row.id}`}
                  className="btn-secondary whitespace-nowrap px-md"
                >
                  Report a problem
                </Link>
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </Card>
  )
}
