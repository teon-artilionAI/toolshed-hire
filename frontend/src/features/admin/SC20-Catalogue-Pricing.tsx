/**
 * SC-20 Catalogue and Pricing Management.
 *
 * Two things live here, both read from the API. The categories customers
 * browse by, and the product models with the figures that decide what a hire
 * earns and what it costs when it goes wrong. The daily and weekly rates, the
 * deposit, the late fee and the replacement value are set once for all three
 * branches.
 *
 * The browser holds no copy of the rules about money, codes or nesting. It
 * shows what the server sends and what the server refuses, each refusal under
 * the field it names. A change of a figure reaches new bookings only, because
 * every booking and hire keeps its own copy, and the screen says so before
 * anything is saved.
 *
 * The search, the filters, the page and the model open in the form live in
 * the address, read and written by catalogue-address.ts, so a reload or a
 * shared link opens the same view. Every write asks first and says what it
 * did in a notice that takes focus, and the lists are read again with the
 * change in them.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { adminQueries } from '../../shared/api/admin-queries'
import type { AdminModel } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { Card, Notice, PageHeader } from '../../shared/ui'
import { NEW_MODEL, readCatalogueFilters, writeCatalogueFilters } from './catalogue-address'
import type { CatalogueFilters } from './catalogue-address'
import { editModelButtonId } from './catalogue-labels'
import { FIRST_PAGE } from './report-address'
import CategoryManager from './SC20-Category-Manager'
import type { CategoryOutcome } from './SC20-Category-Manager'
import { ModelEditor } from './SC20-Model-Editor'
import ModelList from './SC20-Model-List'

/** What the screen says once a write has worked. */
type Outcome = CategoryOutcome

function savedOutcome(saved: AdminModel, added: boolean, movedAFigure: boolean): Outcome {
  if (added) {
    return {
      title: `${saved.name} is in the catalogue`,
      body: 'It is hidden from customers until you publish it. The list below now shows it by its stock code.',
    }
  }
  return {
    title: `${saved.name} is saved`,
    body: movedAFigure
      ? 'New bookings take the new figures. Bookings already made keep the ones they were booked at.'
      : 'The list below shows it as it is now.',
  }
}

function publicationOutcome(model: AdminModel, published: boolean): Outcome {
  return published
    ? { title: `${model.name} is published`, body: 'Customers can find it in the catalogue and book it.' }
    : {
        title: `${model.name} is hidden from customers`,
        body: 'Nobody can book it until it is published again. Bookings already made still stand.',
      }
}

export default function CataloguePricing() {
  const [params, setParams] = useSearchParams()
  const filters = readCatalogueFilters(params)
  const categories = useQuery(adminQueries.categories())
  const categoriesPhase = queryPhase(categories)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const outcomeRef = useRef<HTMLDivElement>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  // The model whose form was closed unsaved, so focus can go back to its button.
  const closedUnsaved = useRef<string | null>(null)

  /** Change what the address says. What is not named keeps its value. */
  const show = useCallback(
    (changes: Partial<CatalogueFilters>) =>
      setParams((current) => writeCatalogueFilters({ ...readCatalogueFilters(current), ...changes }), { replace: true }),
    [setParams],
  )

  useEffect(() => {
    if (outcome !== null) outcomeRef.current?.focus()
  }, [outcome])

  useEffect(() => {
    if (filters.model !== null || closedUnsaved.current === null) return
    const closed = closedUnsaved.current
    closedUnsaved.current = null
    if (closed === NEW_MODEL) addButton.current?.focus()
    else document.getElementById(editModelButtonId(closed))?.focus()
  }, [filters.model])

  function open(model: string) {
    setOutcome(null)
    show({ model })
  }

  function closeEditor() {
    closedUnsaved.current = filters.model
    show({ model: null })
  }

  function saved(model: AdminModel, movedAFigure: boolean) {
    const added = filters.model === NEW_MODEL
    show(added ? { model: null, q: model.sku, categoryId: null, published: null, page: FIRST_PAGE } : { model: null })
    setOutcome(savedOutcome(model, added, movedAFigure))
  }

  return (
    <>
      <PageHeader
        screenId="SC-20"
        title="Catalogue and pricing"
        subtitle="What customers can see, and what each model earns and costs. A new figure reaches new bookings only. Bookings already made keep the figures they were booked at."
        actions={
          <button ref={addButton} type="button" className="btn-primary px-md" onClick={() => open(NEW_MODEL)}>
            <Plus className="h-4 w-4 shrink-0" aria-hidden="true" />
            Add a model
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

      {filters.model !== null && (
        <ModelEditor
          editing={filters.model}
          categories={categories.data?.items}
          categoriesFailure={categoriesPhase === 'failed' ? categories.error : null}
          retryCategories={() => void categories.refetch()}
          onSaved={saved}
          onClose={closeEditor}
        />
      )}

      <div className="mb-lg">
        <Card title="Models in the catalogue">
          <ModelList
            filters={filters}
            categories={categories.data?.items}
            categoriesFailed={categoriesPhase === 'failed'}
            retryCategories={() => void categories.refetch()}
            onShow={show}
            onAdd={() => open(NEW_MODEL)}
            onEdit={(model) => open(model.id)}
            onPublication={(model, published) => setOutcome(publicationOutcome(model, published))}
          />
        </Card>
      </div>

      <CategoryManager
        list={categories.data}
        phase={categoriesPhase}
        error={categories.error}
        onRetry={() => void categories.refetch()}
        onDone={setOutcome}
      />
    </>
  )
}
