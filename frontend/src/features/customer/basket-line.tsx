/**
 * One line of the hire basket on SC-04.
 *
 * The basket knows a model by its slug and how many are wanted. The name and
 * the rates come from the catalogue route for that model, so the line shows
 * what the catalogue says today. It shows no total. The server prices the
 * basket in the next step, and until then there is no figure to show.
 *
 * A model the catalogue no longer has says so on its line and offers to take
 * itself off, because a booking that still names it would be refused.
 */

import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { MAX_QUANTITY, MIN_QUANTITY } from '../../shared/api/catalogue'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { queryPhase } from '../../shared/api/query-phase'
import type { BasketLine as Line, BasketTerms } from '../../shared/basket-store'
import { money } from '../../shared/format'
import { isNotFound } from './booking-refusal'
import { modelDetailHref } from './catalogue-links'
import { QuantityStepper } from './catalogue-ui'

const NAME_WHILE_LOADING = 'this tool'

export default function BasketLine({
  line,
  terms,
  error,
  disabled,
  onChangeQuantity,
  onRemove,
}: {
  line: Line
  /** The period and the branch of the basket, carried on the link to the model. */
  terms: BasketTerms
  /** Why the API refused this line, when it did. */
  error?: string
  /** True while a request is in flight, so the basket cannot change under it. */
  disabled: boolean
  onChangeQuantity: (modelSlug: string, quantity: number) => void
  onRemove: (modelSlug: string) => void
}) {
  const model = useQuery(catalogueQueries.model(line.modelSlug))
  const phase = queryPhase(model)
  const withdrawn = phase === 'failed' && isNotFound(model.error)
  const name = model.data?.name ?? NAME_WHILE_LOADING

  return (
    <li className="border-b border-line pb-lg last:border-0 last:pb-0" aria-busy={phase === 'loading'}>
      <div className="flex flex-wrap items-start justify-between gap-md">
        <div className="min-w-0">
          {model.data ? (
            <>
              <Link
                to={modelDetailHref(line.modelSlug, { from: terms.from, to: terms.to }, terms.branchCode)}
                className="inline-flex min-h-[2.75rem] cursor-pointer items-center text-base font-semibold text-ink underline decoration-line underline-offset-4 transition-colors duration-200 hover:decoration-accent"
              >
                {model.data.name}
              </Link>
              <p className="tabular mt-xs text-sm text-slate-soft">
                {money(model.data.dailyRate)} per day, {money(model.data.depositAmount)} deposit
                each
              </p>
            </>
          ) : (
            <>
              <p className="font-mono text-sm text-ink">{line.modelSlug}</p>
              <p className="mt-xs text-sm text-slate-soft" role={withdrawn ? 'alert' : undefined}>
                {phase === 'loading' && 'Loading the name and the rates of this tool.'}
                {withdrawn &&
                  'We no longer hire this tool. Take it off the basket before you carry on.'}
                {phase === 'failed' &&
                  !withdrawn &&
                  'We could not load the name and the rates of this tool. You can still book it.'}
              </p>
            </>
          )}
        </div>
        <button
          type="button"
          className="btn-ghost px-md"
          disabled={disabled}
          onClick={() => onRemove(line.modelSlug)}
        >
          <Trash2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          Remove{' '}
          <span className="sr-only">{name} from the basket</span>
        </button>
      </div>

      <fieldset className="mt-md" disabled={disabled}>
        <legend className="sr-only">How many of {name}</legend>
        <QuantityStepper
          id={`qty-${line.modelSlug}`}
          itemLabel={name}
          value={line.quantity}
          min={MIN_QUANTITY}
          max={MAX_QUANTITY}
          onChange={(next) => onChangeQuantity(line.modelSlug, next)}
          error={error}
        />
      </fieldset>
    </li>
  )
}
