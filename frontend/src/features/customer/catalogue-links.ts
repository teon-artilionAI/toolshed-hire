/**
 * The addresses the catalogue screens link to one another by.
 *
 * A model is addressed by its slug. Every link to SC-03 is built here, so the
 * shape of that address is decided in one place, and every value that goes
 * into an address is encoded on the way in.
 */

/** The dates a link carries from one screen to the next. */
export interface LinkPeriod {
  from: string
  to: string
}

/**
 * The address of SC-03 for one model.
 *
 * @param slug The model's slug, as the API sent it.
 * @param period The dates the customer has chosen, carried along.
 * @param branchCode The branch the customer has chosen, when there is one.
 */
export function modelDetailHref(slug: string, period: LinkPeriod, branchCode?: string): string {
  const params = new URLSearchParams({ from: period.from, to: period.to })
  if (branchCode) params.set('branch', branchCode)
  return `/model/${encodeURIComponent(slug)}?${params.toString()}`
}

/**
 * The address of SC-02 for a period, optionally narrowed to one category.
 *
 * @param categorySlug The slug of the category to open the search on.
 */
export function searchHref(period: LinkPeriod, categorySlug?: string): string {
  const params = new URLSearchParams({ from: period.from, to: period.to })
  if (categorySlug) params.set('category', categorySlug)
  return `/search?${params.toString()}`
}
