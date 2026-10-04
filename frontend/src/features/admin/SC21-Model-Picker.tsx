/**
 * A product model chosen by searching for it, on SC-21. The register's model
 * filter and the registration form both use it.
 *
 * The catalogue holds more models than one page of the largest size the API
 * serves, and it grows, so a menu of every model would mean reading every page
 * each time and scrolling a menu of hundreds. So the owner types part of the
 * name or the stock code, and the menu below lists the first page of the
 * models that match, from `GET /api/admin/models`, the same read SC-20 lists
 * its models with. The search asks a moment after the last key and not before
 * two characters, the shortest search that route takes.
 *
 * A model already chosen, from the address or earlier, stays in the menu by
 * its own read, `GET /api/admin/models/{id}`, so it is never dropped when it
 * is not among the matches. The line under the menu says what the search
 * found, and it is the menu's description, so a screen reader hears it there.
 */

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RotateCw } from 'lucide-react'
import { adminQueries } from '../../shared/api/admin-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { SelectInput, TextInput } from '../counter/counter-fields'
import { countOf } from '../counter/counter-labels'

/** How long the search waits after the last key before it asks. */
const SEARCH_DEBOUNCE_MS = 300

/** The shortest search the models route takes. */
const SHORTEST_SEARCH = 2

/** How many matches the menu lists. */
const MATCHES_LISTED = 20

const FIRST_PAGE = 1

const NO_MODEL = ''

/** A model as the menu names it. */
export interface PickedModel {
  id: string
  name: string
}

function searchWords(phase: string, typedEnough: boolean, total: number | undefined): string {
  if (!typedEnough) return 'Type two characters or more of the name or stock code above, and the models that match are listed here.'
  if (phase === 'loading') return 'Looking for the models that match.'
  if (phase === 'failed') return 'The models could not be read. Search again to try once more.'
  if (total === undefined) return ''
  if (total === 0) return 'No model matches that search.'
  const found = countOf(total, 'model matches', 'models match')
  return total > MATCHES_LISTED ? `${found}. The first ${MATCHES_LISTED} are listed, so type more to narrow it.` : `${found}.`
}

export function ModelPicker({
  id,
  legend,
  searchLabel,
  selectLabel,
  noChoice,
  chosenId,
  onChoose,
  error,
  disabled = false,
}: {
  /** Unique on the page. The two controls are named from it. */
  id: string
  legend: string
  searchLabel: string
  selectLabel: string
  /** The first entry of the menu, which chooses no model. */
  noChoice: string
  /** The key of the model chosen, or an empty string for none. */
  chosenId: string
  onChoose: (model: PickedModel | null) => void
  error?: string
  disabled?: boolean
}) {
  const [typed, setTyped] = useState('')
  const [searched, setSearched] = useState('')
  useEffect(() => {
    const wanted = typed.trim()
    if (wanted === searched) return
    const timer = window.setTimeout(() => setSearched(wanted), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [typed, searched])

  const typedEnough = searched.length >= SHORTEST_SEARCH
  const matches = useQuery({
    ...adminQueries.models({ q: searched, page: FIRST_PAGE, pageSize: MATCHES_LISTED }),
    enabled: typedEnough,
  })
  const chosen = useQuery({ ...adminQueries.model(chosenId), enabled: chosenId !== NO_MODEL })
  const phase = queryPhase(matches)

  const listed = typedEnough ? (matches.data?.items ?? []) : []
  const keepChosen = chosenId !== NO_MODEL && !listed.some((model) => model.id === chosenId)
  const chosenName = chosen.data?.name ?? 'The model already chosen'
  const options = [
    { value: NO_MODEL, label: noChoice },
    ...(keepChosen ? [{ value: chosenId, label: chosenName }] : []),
    ...listed.map((model) => ({ value: model.id, label: `${model.name} (${model.sku})` })),
  ]

  function choose(value: string) {
    if (value === NO_MODEL) return onChoose(null)
    const match = listed.find((model) => model.id === value)
    onChoose({ id: value, name: match?.name ?? chosenName })
  }

  return (
    <fieldset className="min-w-0">
      <legend className="field-label">{legend}</legend>
      <div className="grid gap-md sm:grid-cols-2">
        <TextInput
          id={`${id}-search`}
          label={searchLabel}
          type="search"
          value={typed}
          onChange={setTyped}
          autoComplete="off"
          disabled={disabled}
        />
        <SelectInput
          id={id}
          label={selectLabel}
          value={chosenId}
          onChange={choose}
          options={options}
          help={searchWords(phase, typedEnough, matches.data?.total)}
          error={error}
          disabled={disabled}
        />
      </div>
      {typedEnough && phase === 'failed' && (
        <button type="button" className="btn-ghost mt-sm px-sm" onClick={() => void matches.refetch()}>
          <RotateCw className="h-4 w-4 shrink-0" aria-hidden="true" />
          Search the models again
        </button>
      )}
    </fieldset>
  )
}
