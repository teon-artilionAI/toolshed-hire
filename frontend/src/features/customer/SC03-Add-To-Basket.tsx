/**
 * The "Add to my hire basket" button on SC-03, and what follows a press.
 *
 * The button only works once the server has answered both questions for the
 * dates, the branch and the quantity on the card. The quote came back, and the
 * branch can supply that many for the whole period. Until then there is
 * nothing honest to add.
 *
 * A press that works says so, names what went in, and offers the basket.
 *
 * A basket is for one period at one branch. When the card is on other dates or
 * another branch than the basket, nothing is added. The person is asked which
 * to keep, and focus moves to that question so it cannot be missed.
 */

import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShoppingCart } from 'lucide-react'
import type { Branch, ModelDetail } from '../../shared/api/contract'
import { addToBasket } from '../../shared/basket-store'
import type { BasketAddition, BasketTerms } from '../../shared/basket-store'
import { Notice } from '../../shared/ui'
import { describePeriod } from './hire-period'

const HINT_ID = 'detail-add-hint'
const CONFLICT_HEADING_ID = 'detail-basket-conflict'

/** What the last press put in the basket, in the words shown to the person. */
interface AddedNote {
  summary: string
  /** How many of this model the basket now holds, when that is more than the
   *  press added. Null when the press put in everything the basket holds. */
  nowHolds: number | null
}

function units(count: number): string {
  return `${count} ${count === 1 ? 'unit' : 'units'}`
}

function termsKey(terms: BasketTerms, modelSlug: string, quantity: number): string {
  return [terms.from, terms.to, terms.branchCode, modelSlug, quantity].join('|')
}

export default function AddToBasket({
  model,
  startIso,
  endIso,
  branchCode,
  quantity,
  branches,
  canAdd,
  onUseBasketTerms,
}: {
  model: ModelDetail
  startIso: string
  endIso: string
  branchCode: string
  quantity: number
  /** Every branch, for the name behind a code. */
  branches: readonly Branch[]
  /** True once the quote and a "free" from the chosen branch have both arrived
   *  for exactly these dates and this quantity. */
  canAdd: boolean
  /** Put the card on the period and branch the basket already has. */
  onUseBasketTerms: (terms: BasketTerms) => void
}) {
  const [added, setAdded] = useState<AddedNote | null>(null)
  const [conflict, setConflict] = useState<{ key: string; basket: BasketTerms } | null>(null)
  const [matched, setMatched] = useState(false)
  const conflictHeading = useRef<HTMLHeadingElement>(null)

  const addition: BasketAddition = {
    modelSlug: model.slug,
    quantity,
    from: startIso,
    to: endIso,
    branchCode,
  }
  const key = termsKey(addition, model.slug, quantity)
  // A question about dates the card has since moved off is no longer the
  // question, so it is only shown while the card still reads the same.
  const openConflict = conflict !== null && conflict.key === key ? conflict : null

  useEffect(() => {
    if (openConflict) conflictHeading.current?.focus()
  }, [openConflict])

  const branchName = (code: string) =>
    branches.find((branch) => branch.code === code)?.name ?? `branch ${code}`
  const where = (terms: BasketTerms) =>
    `${describePeriod(terms.from, terms.to) ?? `${terms.from} to ${terms.to}`}, collected from ${branchName(terms.branchCode)}`

  function noteAdded(inBasket: number) {
    setConflict(null)
    setMatched(false)
    setAdded({
      summary: `${units(quantity)} of ${model.name} for ${where(addition)}.`,
      nowHolds: inBasket === quantity ? null : inBasket,
    })
  }

  function add() {
    if (!canAdd) return
    const result = addToBasket(addition)
    if (result.outcome === 'added') {
      noteAdded(result.quantity)
      return
    }
    setAdded(null)
    setMatched(false)
    setConflict({ key, basket: result.basket })
  }

  function moveBasket() {
    const result = addToBasket(addition, 'moveBasket')
    if (result.outcome === 'added') noteAdded(result.quantity)
  }

  function matchBasket(terms: BasketTerms) {
    setConflict(null)
    setMatched(true)
    onUseBasketTerms(terms)
  }

  return (
    <div className="mt-md">
      <button
        type="button"
        className="btn-primary w-full"
        disabled={!canAdd}
        aria-describedby={canAdd ? undefined : HINT_ID}
        onClick={add}
      >
        <ShoppingCart className="h-4 w-4 shrink-0" aria-hidden="true" />
        Add to my hire basket
      </button>
      {!canAdd && (
        <p id={HINT_ID} className="field-help">
          You can add this once it shows as free at your branch and the price for these dates is
          on the card.
        </p>
      )}

      {openConflict && (
        <div
          role="group"
          aria-labelledby={CONFLICT_HEADING_ID}
          className="mt-md rounded-lg border border-line bg-muted p-md"
        >
          <h3
            id={CONFLICT_HEADING_ID}
            ref={conflictHeading}
            tabIndex={-1}
            className="text-base font-semibold text-ink"
          >
            Your basket is for other dates or another branch
          </h3>
          <p className="mt-xs text-sm text-slate-soft">
            Your basket is for {where(openConflict.basket)}. This tool is for {where(addition)}.
            One hire has one set of dates and one collection branch, so nothing has been added
            yet. Choose which to keep.
          </p>
          <div className="mt-md flex flex-col gap-sm">
            <button
              type="button"
              className="btn-secondary px-md"
              onClick={() => matchBasket(openConflict.basket)}
            >
              Keep my basket, and check this tool for its dates and branch
            </button>
            <button type="button" className="btn-secondary px-md" onClick={moveBasket}>
              Move my whole basket to these dates and this branch
            </button>
            <button type="button" className="btn-ghost px-md" onClick={() => setConflict(null)}>
              Do not add this tool
            </button>
          </div>
        </div>
      )}

      <div role="status" className="mt-md">
        {matched && !added && (
          <p className="text-sm text-slate-soft">
            The dates and the branch above now match your basket. Add the tool once it shows as
            free.
          </p>
        )}
      </div>

      {added && (
        <div className="mt-md">
          <Notice tone="success" title="Added to your hire basket">
            <p>{added.summary}</p>
            {added.nowHolds !== null && (
              <p className="mt-xs">Your basket now holds {added.nowHolds} of this tool.</p>
            )}
            <Link to="/basket" className="btn-secondary mt-sm px-md">
              Go to my basket
            </Link>
          </Notice>
        </div>
      )}
    </div>
  )
}
