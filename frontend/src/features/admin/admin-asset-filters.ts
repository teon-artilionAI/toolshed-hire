/**
 * What "find me this unit" means on SC-21.
 *
 * The filter contract and the matching rule live together so the controls
 * and the list cannot drift apart, and so a filter that is added later is
 * added in one place rather than two.
 */

import type { Asset, ProductModel } from '../../shared/types'

export interface AssetFilterState {
  /** Free text against the asset tag, the tool name and the manufacturer. */
  search: string
  /** A branch code, or ALL. */
  branch: string
  /** An AssetStatus, or ALL. */
  status: string
  /** A category id, or ALL. */
  category: string
}

export const ANY = 'ALL'

export const NO_FILTERS: AssetFilterState = {
  search: '',
  branch: ANY,
  status: ANY,
  category: ANY,
}

export function matchesFilters(
  asset: Asset,
  model: ProductModel | undefined,
  filters: AssetFilterState,
): boolean {
  if (filters.branch !== ANY && asset.branchCode !== filters.branch) return false
  if (filters.status !== ANY && asset.status !== filters.status) return false
  if (filters.category !== ANY && model?.categoryId !== filters.category) return false

  const needle = filters.search.trim().toLowerCase()
  if (!needle) return true
  return (
    asset.tag.toLowerCase().includes(needle) ||
    (model?.name ?? '').toLowerCase().includes(needle) ||
    (model?.manufacturer ?? '').toLowerCase().includes(needle)
  )
}
