/**
 * One unit on SC-21, in a section of its own above the register.
 *
 * The unit is read by its own route, `GET /api/admin/assets/{tag}`, with its
 * history, so the section shows the unit as the server holds it now and not a
 * row of the list. A unit a write answered with is already in the cache under
 * its tag. The read has the shared loading and failed states, and a tag the
 * server does not know says so plainly. The tag comes from the address, which
 * anybody can write.
 *
 * The section holds the unit's fields, the moves it may make, its paperwork
 * with a form to change it, and its history, each under a heading of its own.
 * Its heading takes focus when it opens, so a keyboard carries on from the
 * top of the unit.
 */

import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil, X } from 'lucide-react'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AdminAssetDetail, AssetStatus } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { EmptyState } from '../../shared/ui'
import { isNotOnFile } from '../counter/counter-refusal'
import { AssetEdit } from './SC21-Asset-Edit'
import { AssetFacts } from './SC21-Asset-Facts'
import { AssetHistory } from './SC21-Asset-History'
import { AssetMoves } from './SC21-Asset-Moves'

const HEADING_ID = 'asset-detail-heading'

/** What the section tells the screen once a write has worked. */
export interface UnitHandlers {
  onMoved: (unit: AdminAssetDetail, to: AssetStatus) => void
  onSaved: (unit: AdminAssetDetail) => void
  onClose: () => void
}

function Frame({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  return (
    <section aria-labelledby={HEADING_ID} className="card mb-lg min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-md border-b border-line px-lg py-md">
        <h2 id={HEADING_ID} ref={heading} tabIndex={-1} className="min-w-0 break-all text-lg font-semibold text-ink">
          {title}
        </h2>
        <button type="button" className="btn-secondary px-md" onClick={onClose}>
          <X className="h-4 w-4 shrink-0" aria-hidden="true" />
          Close the unit
        </button>
      </div>
      <div className="flex flex-col gap-lg p-lg">{children}</div>
    </section>
  )
}

function Part({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="min-w-0">
      <h3 id={id} className="mb-sm text-base font-semibold text-ink">
        {title}
      </h3>
      {children}
    </section>
  )
}

function Unit({ unit, onMoved, onSaved }: { unit: AdminAssetDetail } & Omit<UnitHandlers, 'onClose'>) {
  const [editing, setEditing] = useState(false)
  const editButton = useRef<HTMLButtonElement>(null)
  const closedUnsaved = useRef(false)
  useEffect(() => {
    if (editing || !closedUnsaved.current) return
    closedUnsaved.current = false
    editButton.current?.focus()
  }, [editing])

  return (
    <>
      <p className="break-words text-sm text-slate-soft">
        {unit.modelName}, at {unit.branchName}.
      </p>
      <AssetFacts unit={unit} />
      <Part id="asset-moves-heading" title="Move it through its life">
        <AssetMoves key={unit.status} unit={unit} onMoved={onMoved} />
      </Part>
      <Part id="asset-paperwork-heading" title="Its paperwork">
        {editing ? (
          <AssetEdit
            unit={unit}
            onSaved={(saved) => {
              setEditing(false)
              onSaved(saved)
            }}
            onClose={() => {
              closedUnsaved.current = true
              setEditing(false)
            }}
          />
        ) : (
          <button ref={editButton} type="button" className="btn-secondary px-md" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
            Change the serial number, grade, meter reading or notes
          </button>
        )}
      </Part>
      <Part id="asset-history-heading" title="History">
        <AssetHistory unit={unit} />
      </Part>
    </>
  )
}

export function AssetDetail({ tag, onClose, ...handlers }: UnitHandlers & { tag: string }) {
  const read = useQuery(adminQueries.asset(tag))
  const phase = queryPhase(read)
  // Once the unit is on the screen it stays, so a later read in the background
  // that fails never takes away a question or a form that is open.
  if (read.data !== undefined) {
    return (
      <Frame title={`Unit ${read.data.assetTag}`} onClose={onClose}>
        <Unit unit={read.data} {...handlers} />
      </Frame>
    )
  }
  if (phase === 'failed' && isNotOnFile(read.error)) {
    return (
      <Frame title="That unit is not on the register" onClose={onClose}>
        <EmptyState
          title={`No unit carries the tag ${tag}`}
          body="The address may be old or mistyped. Close the unit and find it in the register."
        />
      </Frame>
    )
  }
  return (
    <Frame title={`Opening unit ${tag}`} onClose={onClose}>
      {phase === 'failed' ? (
        <ErrorState what="the unit" error={read.error} onRetry={() => void read.refetch()} />
      ) : (
        <LoadingState label="Loading the unit." shape="detail" count={1} />
      )}
    </Frame>
  )
}
