/**
 * The history of a unit on SC-21, as the server sends it with the unit.
 *
 * The newest entry first, each with when it happened in branch time, what it
 * is about, and the server's own sentence. A booking, a hire or a damage
 * report it belongs to is a link to the screen where that is dealt with. The
 * events the register itself wrote can be read in full in the audit trail,
 * narrowed to this unit.
 */

import { Link } from 'react-router-dom'
import type { AdminAssetDetail } from '../../shared/api/contract'
import { branchDateTime } from '../../shared/today'
import { HISTORY_KIND_LABEL, historyLink, unitTrailHref } from './asset-words'

export function AssetHistory({ unit }: { unit: AdminAssetDetail }) {
  return (
    <>
      <p className="text-sm text-slate-soft">
        The newest first.{' '}
        <Link to={unitTrailHref(unit)} className="inline-flex min-h-[2.75rem] items-center underline">
          Open the events of {unit.assetTag} in the audit trail
        </Link>
      </p>
      {unit.history.length === 0 ? (
        <p className="mt-sm text-sm text-ink">Nothing has happened to this unit yet.</p>
      ) : (
        <ol className="mt-sm flex flex-col divide-y divide-line" aria-label={`The history of ${unit.assetTag}`}>
          {unit.history.map((entry, index) => {
            const link = historyLink(entry, unit.assetTag)
            return (
              <li key={`${entry.at}-${index}`} className="min-w-0 py-sm">
                <p className="flex flex-wrap items-baseline gap-x-md gap-y-xs text-sm">
                  <span className="font-semibold text-ink">{HISTORY_KIND_LABEL[entry.kind]}</span>
                  <span className="tabular text-slate-soft">{branchDateTime(entry.at)}</span>
                </p>
                <p className="mt-xs break-words text-sm text-ink">{entry.summary}</p>
                {link !== null && (
                  <Link to={link.href} className="inline-flex min-h-[2.75rem] items-center text-sm underline">
                    {link.label}
                  </Link>
                )}
                {link === null && entry.reference !== null && (
                  <p className="mt-xs break-all font-mono text-xs text-slate-soft">{entry.reference}</p>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </>
  )
}
