/**
 * Page controls for a list that the server pages.
 *
 * It is a navigation landmark with its own name, so a screen reader user can
 * jump to it. The current page is marked with `aria-current` and also written
 * out as "Page 2 of 5" in a polite status, so moving between pages is
 * announced. Every control is a real button at the full 44 pixel target, and
 * the current page is told apart by its border and weight, not by colour alone.
 */

import { ChevronLeft, ChevronRight } from 'lucide-react'

/** How many page numbers sit either side of the current one. */
const SIBLING_PAGES = 1

/** A gap in the run of page numbers. */
const GAP = 'gap'

type PageItem = number | typeof GAP

/**
 * The page numbers to draw. The first, the last, the current page and its
 * neighbours, with a gap wherever numbers were left out.
 */
function pageItems(current: number, pageCount: number): PageItem[] {
  const wanted = new Set<number>([1, pageCount])
  for (let page = current - SIBLING_PAGES; page <= current + SIBLING_PAGES; page += 1) {
    if (page >= 1 && page <= pageCount) wanted.add(page)
  }
  const pages = [...wanted].sort((a, b) => a - b)
  const items: PageItem[] = []
  pages.forEach((page, index) => {
    if (index > 0 && page - pages[index - 1] > 1) items.push(GAP)
    items.push(page)
  })
  return items
}

/** How many pages a total splits into. Never fewer than one. */
function pageCountFor(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)))
}

export default function Pagination({
  label,
  page,
  pageSize,
  total,
  onPageChange,
}: {
  /** Names the landmark, for example "Search result pages". */
  label: string
  /** The current page, counted from 1. */
  page: number
  /** How many items the server puts on a page. */
  pageSize: number
  /** How many items there are across every page. */
  total: number
  onPageChange: (page: number) => void
}) {
  const pageCount = pageCountFor(total, pageSize)
  if (pageCount <= 1) return null
  const current = Math.min(Math.max(1, page), pageCount)

  return (
    <nav aria-label={label} className="mt-lg flex flex-wrap items-center justify-between gap-md">
      <p className="tabular text-sm text-slate-soft" role="status">
        Page {current} of {pageCount}
      </p>
      <ul className="flex flex-wrap items-center gap-sm">
        <li>
          <button
            type="button"
            className="btn-secondary px-md"
            onClick={() => onPageChange(current - 1)}
            disabled={current <= 1}
          >
            <ChevronLeft className="h-4 w-4 shrink-0" aria-hidden="true" />
            Previous
          </button>
        </li>
        {pageItems(current, pageCount).map((item, index) =>
          item === GAP ? (
            <li key={`gap-${index}`} aria-hidden="true" className="px-xs text-slate-soft">
              …
            </li>
          ) : (
            <li key={item}>
              <button
                type="button"
                className={
                  item === current
                    ? 'btn tabular border-2 border-ink bg-surface font-semibold text-ink'
                    : 'btn-secondary tabular'
                }
                aria-current={item === current ? 'page' : undefined}
                aria-label={`Page ${item}`}
                onClick={() => onPageChange(item)}
              >
                {item}
              </button>
            </li>
          ),
        )}
        <li>
          <button
            type="button"
            className="btn-secondary px-md"
            onClick={() => onPageChange(current + 1)}
            disabled={current >= pageCount}
          >
            Next
            <ChevronRight className="h-4 w-4 shrink-0" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </nav>
  )
}
