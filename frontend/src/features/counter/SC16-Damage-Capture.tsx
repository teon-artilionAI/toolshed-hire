/**
 * SC-16 Damage Report Capture.
 *
 * Raised from the return inspection when a unit comes back worse than it went
 * out. Recording damage takes the unit off hire immediately: it moves to
 * quarantine and stops appearing as available stock, which is the whole point
 * of capturing it at the counter rather than in a notebook.
 *
 * Photographs are chosen but not uploaded. There is no back end in the
 * prototype and the screen says so rather than implying a file went
 * somewhere.
 */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ShieldAlert } from 'lucide-react'
import {
  assets,
  branches,
  damageReports,
  productModels,
} from '../../shared/fixtures'
import type { DamageReport } from '../../shared/types'
import { formatDate, humanise, money } from '../../shared/format'
import { Card, Field, Notice, PageHeader, StatusPill } from '../../shared/ui'
import {
  ChargeableChoice,
  PhotographPicker,
  SeverityChoice,
} from './SC16-DamageFields'
import type { Severity } from './SC16-DamageFields'
import { DamageRecorded } from './SC16-DamageRecorded'

const MIN_DESCRIPTION_LENGTH = 20

interface FormErrors {
  severity?: string
  description?: string
  estimate?: string
  chargeable?: string
}

export default function DamageReportCapture() {
  const { assetId } = useParams()
  const asset = assets.find((a) => a.id === assetId || a.tag === assetId)

  if (!asset) {
    return (
      <>
        <PageHeader
          screenId="SC-16"
          title="Record damage"
          subtitle="We could not find that unit."
        />
        <Notice tone="error" title={`No asset matches "${assetId ?? ''}"`}>
          Check the tag on the unit itself. It is on the metal plate near the
          handle. If the tag is missing or unreadable, look the unit up by model
          in the asset locator.
        </Notice>
        <Link to="/counter/locator" className="btn-primary mt-md px-md">
          Open the asset locator
        </Link>
      </>
    )
  }

  return <DamageForm key={asset.id} assetKey={asset.id} />
}

function DamageForm({ assetKey }: { assetKey: string }) {
  const asset = assets.find((a) => a.id === assetKey)!
  const model = productModels.find((m) => m.id === asset.productModelId)
  const branch = branches.find((b) => b.code === asset.branchCode)
  const history: DamageReport[] = damageReports.filter((d) => d.assetId === asset.id)

  const [severity, setSeverity] = useState<Severity | null>(null)
  const [description, setDescription] = useState('')
  const [photographs, setPhotographs] = useState<string[]>([])
  const [estimate, setEstimate] = useState('')
  const [chargeable, setChargeable] = useState<boolean | null>(null)
  const [errors, setErrors] = useState<FormErrors>({})
  const [saved, setSaved] = useState(false)

  const estimateValue = Number.parseFloat(estimate)
  const replacementValue = model?.replacementValue ?? 0
  const beyondEconomicRepair =
    Number.isFinite(estimateValue) && estimateValue > replacementValue && replacementValue > 0

  function validate(): FormErrors {
    const next: FormErrors = {}
    if (!severity) next.severity = 'Choose how bad the damage is.'
    if (description.trim().length < MIN_DESCRIPTION_LENGTH) {
      next.description =
        'Describe what is actually broken, in at least twenty characters. The workshop works from this and nothing else.'
    }
    if (!Number.isFinite(estimateValue) || estimateValue <= 0) {
      next.estimate = 'Enter an estimated repair cost in rand. Put your best guess if the workshop has not quoted yet.'
    }
    if (chargeable === null) next.chargeable = 'Say whether the customer is being charged.'
    return next
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length === 0) setSaved(true)
  }

  if (saved && severity) {
    return (
      <DamageRecorded
        tag={asset.tag}
        modelName={model?.name ?? 'this unit'}
        severity={severity}
        estimate={estimateValue}
        chargeable={chargeable === true}
        photographs={photographs.length}
        assetId={asset.id}
      />
    )
  }

  const errorList = Object.values(errors)

  return (
    <>
      <PageHeader
        screenId="SC-16"
        title="Record damage"
        subtitle={`${asset.tag}, ${model?.manufacturer ?? ''} ${model?.name ?? ''} at ${branch?.name ?? asset.branchCode}.`}
        actions={<StatusPill status={asset.status} />}
      />

      {history.length > 0 && (
        <div className="mb-lg">
          <Card title="Already on this unit's record">
            <ul className="flex flex-col gap-sm">
              {history.map((report) => (
                <li key={report.id} className="flex flex-wrap items-start gap-sm">
                  <StatusPill status={report.status} />
                  <p className="min-w-0 flex-1 text-sm text-slate-soft">
                    {humanise(report.severity)}, {formatDate(report.raisedAt)}.{' '}
                    {report.description}
                  </p>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      <form onSubmit={submit} noValidate>
        <Card title="What happened">
          {errorList.length > 0 && (
            <div className="mb-lg">
              <Notice tone="error" title="This report is not ready to save">
                <ul className="ml-md list-disc">
                  {errorList.map((message) => (
                    <li key={message}>{message}</li>
                  ))}
                </ul>
              </Notice>
            </div>
          )}

          <div className="flex flex-col gap-lg">
            <SeverityChoice
              value={severity}
              onChange={setSeverity}
              error={errors.severity}
            />

            <Field
              label="Describe the damage"
              htmlFor="damage-description"
              help="What is broken, how it happened if you know, and whether the unit still runs."
              error={errors.description}
            >
              <textarea
                id="damage-description"
                rows={4}
                className="field-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Guard bracket sheared where it bolts to the housing. The unit starts but the guard moves under load."
              />
            </Field>

            <PhotographPicker files={photographs} onChange={setPhotographs} />

            <Field
              label="Estimated repair cost, in rand"
              htmlFor="damage-estimate"
              help={
                replacementValue > 0
                  ? `Replacing this unit costs ${money(replacementValue)}.`
                  : undefined
              }
              error={errors.estimate}
            >
              <input
                id="damage-estimate"
                type="number"
                inputMode="decimal"
                min={0}
                step="0.01"
                className="field-input tabular"
                value={estimate}
                onChange={(e) => setEstimate(e.target.value)}
                placeholder="0.00"
              />
            </Field>

            {beyondEconomicRepair && (
              <Notice tone="warn" title="That is more than the unit is worth">
                {money(estimateValue)} to repair against {money(replacementValue)}
                {' '}to replace. Flag it to the owner as a write-off rather than
                booking workshop time.
              </Notice>
            )}

            <ChargeableChoice
              value={chargeable}
              onChange={setChargeable}
              error={errors.chargeable}
            />
          </div>

          <div className="mt-lg flex flex-wrap gap-sm border-t border-line pt-md">
            <button type="submit" className="btn-primary px-md">
              <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
              Record the damage and quarantine the unit
            </button>
            <Link to="/counter/locator" className="btn-secondary px-md">
              Cancel
            </Link>
          </div>
        </Card>
      </form>
    </>
  )
}
