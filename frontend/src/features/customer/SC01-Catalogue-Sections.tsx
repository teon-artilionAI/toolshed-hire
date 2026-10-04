/**
 * The three parts of SC-01 that are filled from the API.
 *
 * Each part owns its own loading, failed and empty states, so a slow or failed
 * list never takes the search form or the other lists down with it. A customer
 * can always pick dates and search, whatever else is still on its way.
 */

import { Link } from 'react-router-dom'
import type { UseQueryResult } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import type { BranchList, Category, CategoryList, ModelPage } from '../../shared/api/contract'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { money } from '../../shared/format'
import { EmptyState, StatTile } from '../../shared/ui'
import { modelDetailHref, searchHref } from './catalogue-links'
import { categoryIconFor } from './category-icons'
import { ModelBanner } from './model-picture'

/** Skeleton blocks to draw while the categories are on their way. */
const CATEGORY_SKELETON_COUNT = 8

const STAT_TILE_COUNT = 3

/** Writes "Cape Town CBD, Bellville and Somerset West" from the branch names.
 *  A customer knows a branch by its name, not by the suburb it stands in. */
const BRANCH_LIST = new Intl.ListFormat('en-ZA', { style: 'long', type: 'conjunction' })

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

/**
 * The categories the home screen offers and counts.
 *
 * The count the API gives a parent already includes its children. So one tile
 * for each top level category covers the whole catalogue once, and the counts
 * on the tiles add up to the catalogue. A child gets no tile of its own. The
 * search screen offers it in the category menu, under its parent. A category
 * with nothing in it leads to an empty search, so it gets no tile either.
 */
function browsableCategories(categories: Category[]): Category[] {
  return categories.filter((category) => category.parentCode === null && category.modelCount > 0)
}

/** The row of figures under the search form. It waits for all three lists,
 *  and draws nothing if one of them failed, because the part below it that
 *  failed already says so and offers the retry. */
export function CatalogueStats({
  branches,
  categories,
  models,
  days,
  periodLabel,
}: {
  branches: UseQueryResult<BranchList>
  categories: UseQueryResult<CategoryList>
  models: UseQueryResult<ModelPage>
  /** Days in the chosen hire, or null while the dates are unusable. */
  days: number | null
  periodLabel: string | null
}) {
  const phases = [queryPhase(branches), queryPhase(categories), queryPhase(models)]
  if (phases.includes('failed')) return null
  if (!branches.data || !categories.data || !models.data) {
    return (
      <div className="mb-lg">
        <LoadingState label="Loading the catalogue figures" shape="tiles" count={STAT_TILE_COUNT} />
      </div>
    )
  }
  const stockedCategories = browsableCategories(categories.data.items)
  return (
    <div className="mb-lg grid gap-md sm:grid-cols-3">
      <StatTile
        label="Models in the catalogue"
        value={models.data.total}
        hint={`Across ${plural(stockedCategories.length, 'category', 'categories')}`}
      />
      <StatTile
        label="Branches"
        value={branches.data.items.length}
        hint={BRANCH_LIST.format(branches.data.items.map((branch) => branch.name))}
      />
      <StatTile
        label="Days in this hire"
        value={days ?? '...'}
        hint={periodLabel ?? 'Choose your dates above'}
      />
    </div>
  )
}

/** "Browse by job". One tile per top level category that has something to hire. */
export function CategoryGrid({
  categories,
  startIso,
  endIso,
}: {
  categories: UseQueryResult<CategoryList>
  startIso: string
  endIso: string
}) {
  const phase = queryPhase(categories)
  const stocked = browsableCategories(categories.data?.items ?? [])

  return (
    <section className="mb-lg" aria-labelledby="categories-heading">
      <h2 id="categories-heading" className="mb-md text-lg font-semibold text-ink">
        Browse by job
      </h2>
      {phase === 'loading' && (
        <LoadingState label="Loading the categories" shape="links" count={CATEGORY_SKELETON_COUNT} />
      )}
      {phase === 'failed' && (
        <ErrorState
          what="the categories"
          error={categories.error}
          onRetry={() => void categories.refetch()}
        />
      )}
      {phase === 'ready' && stocked.length === 0 && (
        <div className="card">
          <EmptyState
            title="No categories to browse yet"
            body="Nothing is listed for hire right now. Ring your branch and we will tell you what we can get you."
          />
        </div>
      )}
      {phase === 'ready' && stocked.length > 0 && (
        <ul
          className="grid gap-md sm:grid-cols-2 lg:grid-cols-4"
          aria-busy={categories.isFetching}
        >
          {stocked.map((category) => {
            const Icon = categoryIconFor(category.code)
            return (
              <li key={category.code}>
                <Link
                  to={searchHref({ from: startIso, to: endIso }, category.slug)}
                  className="card flex h-full cursor-pointer items-start gap-md p-md transition-shadow duration-200 hover:shadow-raised"
                >
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded bg-accent-wash">
                    <Icon className="h-5 w-5 text-ink" aria-hidden="true" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-base font-semibold text-ink">{category.name}</span>
                    <span className="tabular mt-xs block text-sm text-slate-soft">
                      {plural(category.modelCount, 'model', 'models')}
                    </span>
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** The handful of models the shop window puts up front. */
export function FeaturedModels({
  models,
  count,
  startIso,
  endIso,
}: {
  models: UseQueryResult<ModelPage>
  /** How many models were asked for, so the skeleton matches. */
  count: number
  startIso: string
  endIso: string
}) {
  const phase = queryPhase(models)
  const items = models.data?.items ?? []

  return (
    <section aria-labelledby="featured-heading">
      <div className="mb-md flex flex-wrap items-end justify-between gap-sm">
        <h2 id="featured-heading" className="text-lg font-semibold text-ink">
          From the catalogue
        </h2>
        <Link to={searchHref({ from: startIso, to: endIso })} className="btn-secondary px-md">
          See the full catalogue
          <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
        </Link>
      </div>

      {phase === 'loading' && (
        <LoadingState label="Loading tools from the catalogue" shape="cards" count={count} />
      )}
      {phase === 'failed' && (
        <ErrorState
          what="the catalogue"
          error={models.error}
          onRetry={() => void models.refetch()}
        />
      )}
      {phase === 'ready' && items.length === 0 && (
        <div className="card">
          <EmptyState
            title="Nothing in the catalogue yet"
            body="No tools are listed for hire right now. Ring your branch and we will tell you what we can get you."
          />
        </div>
      )}
      {phase === 'ready' && items.length > 0 && (
        <ul className="grid gap-md sm:grid-cols-2 lg:grid-cols-3" aria-busy={models.isFetching}>
          {items.map((model) => (
            <li key={model.sku}>
              <Link
                to={modelDetailHref(model.slug, { from: startIso, to: endIso })}
                className="card flex h-full cursor-pointer flex-col transition-shadow duration-200 hover:shadow-raised"
              >
                <ModelBanner
                  name={model.name}
                  manufacturer={model.manufacturer}
                  categoryCode={model.categoryCode}
                  imagePath={model.imagePath}
                />
                <div className="flex flex-1 flex-col p-md">
                  <p className="tabular text-lg font-semibold text-ink">
                    {money(model.dailyRate)}
                    <span className="text-sm font-normal text-slate-soft"> per day</span>
                  </p>
                  <p className="mt-xs text-sm text-slate-soft">
                    Deposit {money(model.depositAmount)}
                  </p>
                  <p className="mt-sm flex-1 text-sm text-slate-soft">{model.shortDescription}</p>
                  <span className="mt-md inline-flex items-center gap-xs text-sm font-semibold text-ink">
                    See dates and book
                    <ArrowRight className="h-4 w-4 shrink-0" aria-hidden="true" />
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
