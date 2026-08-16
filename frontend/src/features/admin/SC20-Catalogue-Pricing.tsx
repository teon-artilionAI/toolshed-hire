/**
 * SC-20 Catalogue and Pricing Management.
 *
 * Two things live here: the categories customers browse by, and the
 * product models with the four numbers that decide what a hire earns and
 * what it costs when it goes wrong.
 *
 * Publishing is a rule rather than a switch. An entry with no units on the
 * fleet cannot be published, because a customer would be able to book
 * something the business cannot hand over. The chipper shredder is exactly
 * that case and the screen says so rather than failing quietly.
 */

import { useMemo, useState } from 'react'
import { Eye, EyeOff, Pencil } from 'lucide-react'
import type { Category, ProductModel } from '../../shared/types'
import { assets, categories as seedCategories, productModels } from '../../shared/fixtures'
import {
  Card, DataTable, EmptyState, Field, Notice, PageHeader, StatTile, StatusPill,
} from '../../shared/ui'
import { money } from '../../shared/format'
import { OUT_OF_FLEET } from './admin-fleet'
import CategoryManager from './SC20-Category-Manager'
import ModelForm from './SC20-Model-Form'

type PublishFilter = 'ALL' | 'PUBLISHED' | 'HIDDEN'

/** Units that could actually be handed over. Retired and lost ones cannot. */
function hireableUnits(modelId: string): number {
  return assets.filter((a) => a.productModelId === modelId && !OUT_OF_FLEET.includes(a.status)).length
}

export default function CataloguePricing() {
  const [models, setModels] = useState<ProductModel[]>(productModels)
  const [categories, setCategories] = useState<Category[]>(seedCategories)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('ALL')
  const [publishFilter, setPublishFilter] = useState<PublishFilter>('ALL')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [message, setMessage] = useState('')

  const editing = models.find((m) => m.id === editingId) ?? null
  const hidden = models.filter((m) => !m.published)

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return models.filter((m) => {
      if (categoryFilter !== 'ALL' && m.categoryId !== categoryFilter) return false
      if (publishFilter === 'PUBLISHED' && !m.published) return false
      if (publishFilter === 'HIDDEN' && m.published) return false
      if (!needle) return true
      return (
        m.name.toLowerCase().includes(needle) ||
        m.manufacturer.toLowerCase().includes(needle) ||
        m.sku.toLowerCase().includes(needle)
      )
    })
  }, [models, search, categoryFilter, publishFilter])

  const clearFilters = () => {
    setSearch('')
    setCategoryFilter('ALL')
    setPublishFilter('ALL')
  }

  const togglePublished = (model: ProductModel) => {
    const next = !model.published
    setModels((list) => list.map((m) => (m.id === model.id ? { ...m, published: next } : m)))
    setMessage(
      next
        ? `${model.name} is now in the customer catalogue.`
        : `${model.name} is hidden from customers. Bookings already made still stand.`,
    )
  }

  const saveModel = (updated: ProductModel) => {
    setModels((list) => list.map((m) => (m.id === updated.id ? updated : m)))
    setEditingId(null)
    setMessage(`Rates for ${updated.name} have been saved.`)
  }

  /** Returns null when the category was added, or why it could not be. */
  const addCategory = (name: string): string | null => {
    if (categories.some((c) => c.name.toLowerCase() === name.toLowerCase())) {
      return `There is already a category called ${name}. Choose a different name.`
    }
    setCategories((list) => [
      ...list,
      {
        id: `cat-new-${list.length + 1}`,
        name,
        slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      },
    ])
    setMessage(`${name} has been added as a category.`)
    return null
  }

  const removeCategory = (category: Category) => {
    setCategories((list) => list.filter((c) => c.id !== category.id))
    if (categoryFilter === category.id) setCategoryFilter('ALL')
    setMessage(`${category.name} has been removed.`)
  }

  return (
    <>
      <PageHeader
        screenId="SC-20"
        title="Catalogue and pricing"
        subtitle="What customers can see, and what each tool earns per day. Changes here apply to new bookings only; bookings already made keep the rate they were quoted."
      />

      {/* Notice already carries role="status", so it announces itself once. */}
      {message && (
        <div className="mb-lg">
          <Notice tone="success" title={message} />
        </div>
      )}

      <div className="mb-lg grid gap-md sm:grid-cols-3">
        <StatTile label="Catalogue entries" value={models.length} hint={`Across ${categories.length} categories`} />
        <StatTile
          label="Live to customers"
          value={models.filter((m) => m.published).length}
          hint="Bookable in the customer catalogue"
          tone="good"
        />
        <StatTile
          label="Not published"
          value={hidden.length}
          hint="Hidden from customers until published"
          tone={hidden.length > 0 ? 'warn' : 'good'}
        />
      </div>

      {hidden.length > 0 && (
        <div className="mb-lg">
          <Notice
            tone="warn"
            title={`${hidden.length} catalogue ${hidden.length === 1 ? 'entry is' : 'entries are'} not published`}
          >
            <ul className="list-disc pl-md">
              {hidden.map((m) => (
                <li key={m.id}>
                  <strong>{m.name}</strong>{' '}
                  {hireableUnits(m.id) === 0
                    ? 'cannot be published yet because there are no units on the fleet. Add a unit on the asset register first.'
                    : 'is ready to publish and is waiting for you.'}
                </li>
              ))}
            </ul>
          </Notice>
        </div>
      )}

      {editing && (
        <div className="mb-lg">
          <Card title={`Editing ${editing.name}`}>
            <ModelForm
              key={editing.id}
              model={editing}
              categories={categories}
              takenSkus={models.filter((m) => m.id !== editing.id).map((m) => m.sku.toUpperCase())}
              onSave={saveModel}
              onCancel={() => setEditingId(null)}
            />
          </Card>
        </div>
      )}

      <div className="mb-lg">
        <Card title="Categories">
          <CategoryManager
            categories={categories}
            countFor={(id) => models.filter((m) => m.categoryId === id).length}
            onAdd={addCategory}
            onRemove={removeCategory}
          />
        </Card>
      </div>

      <Card title={`Tools in the catalogue (${shown.length})`}>
        <div className="mb-md grid gap-md sm:grid-cols-3">
          <Field label="Search by name, make or stock code" htmlFor="model-search">
            <input
              id="model-search" type="search" className="field-input" value={search}
              placeholder="Rotary hammer" onChange={(e) => setSearch(e.target.value)}
            />
          </Field>
          <Field label="Category" htmlFor="category-filter">
            <select
              id="category-filter" className="field-input" value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              <option value="ALL">All categories</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Shown to customers" htmlFor="publish-filter">
            <select
              id="publish-filter" className="field-input" value={publishFilter}
              onChange={(e) => setPublishFilter(e.target.value as PublishFilter)}
            >
              <option value="ALL">Published and hidden</option>
              <option value="PUBLISHED">Published only</option>
              <option value="HIDDEN">Not published only</option>
            </select>
          </Field>
        </div>

        {shown.length === 0 ? (
          <EmptyState
            title="No tools match what you asked for"
            body="Nothing in the catalogue matches that search and those filters together. Widen the search or clear the filters and start again."
            action={
              <button type="button" className="btn-secondary px-md" onClick={clearFilters}>
                Clear the filters
              </button>
            }
          />
        ) : (
          <DataTable
            caption="Every catalogue entry with its rates, deposit, late fee and replacement value."
            columns={[
              'Tool', 'Category', 'Units', 'Per day', 'Deposit', 'Late fee per day',
              'Replacement', 'Customers see it', 'Actions',
            ]}
          >
            {shown.map((model) => {
              const units = hireableUnits(model.id)
              const canPublish = units > 0
              return (
                <tr key={model.id} className={model.published ? undefined : 'bg-muted'}>
                  <td className="td">
                    <p className="font-medium text-ink">{model.name}</p>
                    <p className="text-xs text-slate-soft">
                      {model.manufacturer} <span className="font-mono">{model.sku}</span>
                    </p>
                  </td>
                  <td className="td text-slate-soft">
                    {categories.find((c) => c.id === model.categoryId)?.name ?? 'Uncategorised'}
                  </td>
                  <td className="td tabular">{units}</td>
                  <td className="td tabular">{money(model.dailyRate)}</td>
                  <td className="td tabular">{money(model.depositAmount)}</td>
                  <td className="td tabular">{money(model.lateFeePerDay)}</td>
                  <td className="td tabular">{money(model.replacementValue)}</td>
                  <td className="td">
                    <StatusPill
                      status={model.published ? 'AVAILABLE' : 'DRAFT'}
                      label={model.published ? 'Published' : 'Not published'}
                    />
                    {!model.published && !canPublish && (
                      <p className="mt-xs text-xs text-slate-soft">No units on the fleet</p>
                    )}
                  </td>
                  <td className="td">
                    <div className="flex flex-wrap gap-sm">
                      <button
                        type="button"
                        className="btn-secondary px-md text-sm"
                        onClick={() => setEditingId(model.id)}
                      >
                        <Pencil className="h-4 w-4 shrink-0" aria-hidden="true" />
                        Edit
                        <span className="sr-only"> {model.name}</span>
                      </button>
                      <button
                        type="button"
                        disabled={!model.published && !canPublish}
                        className={model.published ? 'btn-secondary px-md text-sm' : 'btn-primary px-md text-sm'}
                        onClick={() => togglePublished(model)}
                      >
                        {model.published ? (
                          <EyeOff className="h-4 w-4 shrink-0" aria-hidden="true" />
                        ) : (
                          <Eye className="h-4 w-4 shrink-0" aria-hidden="true" />
                        )}
                        {model.published ? 'Hide' : 'Publish'}
                        <span className="sr-only"> {model.name}</span>
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </DataTable>
        )}
      </Card>
    </>
  )
}
