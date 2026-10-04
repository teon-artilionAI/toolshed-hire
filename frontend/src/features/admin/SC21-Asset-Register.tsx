/**
 * SC-21 Asset Register and Lifecycle.
 *
 * Every unit the business owns, read from the API, retired units included,
 * because nothing is ever deleted. The owner finds a unit by its tag, serial
 * number or model, by branch, by status and by model, opens it to read its
 * fields, its open damage reports and its history, registers new units,
 * changes their paperwork and moves them through their lifecycle.
 *
 * The browser holds no copy of the lifecycle rules. A unit offers exactly the
 * moves the server lists for it, and whatever the server refuses is shown in
 * its own words. Damage reports are resolved on the damage screen, which each
 * open report links to.
 *
 * The filters, the page, the unit open and the registration form live in the
 * address, read and written by asset-address.ts, so a reload or a shared link
 * opens the same view. Every write asks first and says what it did in a notice
 * that takes focus, and the register is read again with the change in it.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plus } from 'lucide-react'
import type { AdminAssetDetail, AssetStatus } from '../../shared/api/contract'
import { Card, Notice, PageHeader } from '../../shared/ui'
import { ASSET_STATUS_LABEL } from '../counter/counter-labels'
import { openUnitLinkId, readAssetFilters, writeAssetFilters } from './asset-address'
import type { AssetFilters } from './asset-address'
import { AssetDetail } from './SC21-Asset-Detail'
import { AssetRegistration } from './SC21-Asset-Form'
import AssetList from './SC21-Asset-List'

/** What the screen says once a write has worked. */
interface Outcome {
  title: string
  body: string
}

const REGISTER_HEADING_ID = 'asset-register-heading'

function movedOutcome(unit: AdminAssetDetail, to: AssetStatus): Outcome {
  const standing = ASSET_STATUS_LABEL[unit.status].toLowerCase()
  if (to === 'RETIRED') {
    return {
      title: `${unit.assetTag} is retired`,
      body: 'It has left the fleet for good. Its row and its whole history stay on the register.',
    }
  }
  return { title: `${unit.assetTag} is now ${standing}`, body: 'Its history below shows the move.' }
}

function RegistrationSection({ children }: { children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  return (
    <section aria-labelledby={REGISTER_HEADING_ID} className="card mb-lg min-w-0">
      <div className="border-b border-line px-lg py-md">
        <h2 id={REGISTER_HEADING_ID} ref={heading} tabIndex={-1} className="text-lg font-semibold text-ink">
          Register a unit
        </h2>
      </div>
      <div className="p-lg">{children}</div>
    </section>
  )
}

export default function AssetRegister() {
  const [params, setParams] = useSearchParams()
  const filters = readAssetFilters(params)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const outcomeRef = useRef<HTMLDivElement>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  // The unit that was closed, so focus can go back to its link in the list.
  const closedUnit = useRef<string | null>(null)

  /** Change what the address says. What is not named keeps its value. */
  const show = useCallback(
    (changes: Partial<AssetFilters>) =>
      setParams((current) => writeAssetFilters({ ...readAssetFilters(current), ...changes }), { replace: true }),
    [setParams],
  )

  useEffect(() => {
    if (outcome !== null) outcomeRef.current?.focus()
  }, [outcome])

  useEffect(() => {
    if (filters.asset !== null || closedUnit.current === null) return
    const closed = closedUnit.current
    closedUnit.current = null
    document.getElementById(openUnitLinkId(closed))?.focus()
  }, [filters.asset])

  function startRegistering() {
    setOutcome(null)
    show({ adding: true, asset: null })
  }

  function registered(unit: AdminAssetDetail) {
    show({ adding: false, asset: unit.assetTag })
    setOutcome({
      title: `${unit.assetTag} is registered at intake`,
      body: 'Nobody can book it yet. Commission it below once it has been checked.',
    })
  }

  function closeRegistration() {
    show({ adding: false })
    addButton.current?.focus()
  }

  return (
    <>
      <PageHeader
        screenId="SC-21"
        title="Asset register"
        subtitle="Every unit the business owns, where it is and where it stands. A unit only moves to a status the server offers for it, and a retired unit stays on the register with its history."
        actions={
          <button ref={addButton} type="button" className="btn-primary px-md" onClick={startRegistering}>
            <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
            Register a unit
          </button>
        }
      />

      {outcome !== null && (
        <div ref={outcomeRef} tabIndex={-1} className="mb-lg">
          <Notice tone="success" title={outcome.title}>
            <p>{outcome.body}</p>
          </Notice>
        </div>
      )}

      {filters.adding && (
        <RegistrationSection>
          <AssetRegistration onRegistered={registered} onClose={closeRegistration} />
        </RegistrationSection>
      )}

      {filters.asset !== null && (
        <AssetDetail
          key={filters.asset}
          tag={filters.asset}
          onMoved={(unit, to) => setOutcome(movedOutcome(unit, to))}
          onSaved={(unit) =>
            setOutcome({ title: `The details of ${unit.assetTag} are saved`, body: 'Its history below shows the change.' })
          }
          onClose={() => {
            closedUnit.current = filters.asset
            setOutcome(null)
            show({ asset: null })
          }}
        />
      )}

      <Card title="Units on the register">
        <AssetList filters={filters} onShow={show} onAdd={startRegistering} />
      </Card>
    </>
  )
}
