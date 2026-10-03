/**
 * SC-17 Asset Locator.
 *
 * The client's second complaint, answered directly. Staff cannot tell which
 * branch a unit is at without ringing round. Type a tag or part of a model
 * name and the answer is on the screen, across all three branches, with the
 * state each unit is in and the day it is due back when it is out.
 *
 * It is read only and needs no branch. Nothing here changes anything, which is
 * why it can be used one handed while someone is holding on the phone.
 *
 * The search runs on the server from two characters, a moment after the last
 * key, so it never runs on every keystroke. The search and the page live in
 * the address, so a reload brings the same results back. A page in the address
 * that is not a whole number from one falls back to the first.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import { MAX_LOCATOR_SEARCH_LENGTH, MIN_LOCATOR_SEARCH_LENGTH } from '../../shared/api/locator'
import { Field, PageHeader } from '../../shared/ui'
import { FIRST_PAGE, UnitResults } from './SC17-Unit-Results'

/** How long the search waits after the last key before it runs. */
const SEARCH_DEBOUNCE_MS = 300

const QUERY_PARAMETER = 'q'
const PAGE_PARAMETER = 'page'

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

export default function AssetLocator() {
  const [params, setParams] = useSearchParams()
  const searched = (params.get(QUERY_PARAMETER) ?? '').trim()
  const page = readPage(params.get(PAGE_PARAMETER))
  const resultsRef = useRef<HTMLElement>(null)

  /** Write the search and the page to the address. A default is left out. */
  const show = useCallback(
    (q: string, nextPage: number) => {
      const written = new URLSearchParams()
      if (q) written.set(QUERY_PARAMETER, q)
      if (nextPage > FIRST_PAGE) written.set(PAGE_PARAMETER, String(nextPage))
      setParams(written, { replace: true })
    },
    [setParams],
  )

  // The box holds what is being typed and the address holds what was last
  // searched. When the address changes from somewhere else, the box follows.
  const [draft, setDraft] = useState(searched)
  const [lastSearched, setLastSearched] = useState(searched)
  if (searched !== lastSearched) {
    setLastSearched(searched)
    if (searched !== draft.trim()) setDraft(searched)
  }
  useEffect(() => {
    const typed = draft.trim()
    if (typed === searched) return
    const timer = window.setTimeout(() => show(typed, FIRST_PAGE), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [draft, searched, show])

  function goToPage(next: number) {
    show(searched, next)
    // The new page replaces the list, so focus goes to the top of it and a
    // keyboard user reads the new page from its first unit.
    resultsRef.current?.focus()
  }

  return (
    <>
      <PageHeader
        screenId="SC-17"
        title="Where is it"
        subtitle="Search any asset tag or model across all three branches. Nothing on this screen changes anything, so it is safe to use while you are on the phone."
      />

      <div className="mb-lg max-w-xl">
        <Field
          label="Asset tag or model"
          htmlFor="locator-search"
          help={`Part of a tag works too, and "compactor" finds every compactor on the fleet. ${MIN_LOCATOR_SEARCH_LENGTH} characters or more.`}
        >
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-md top-1/2 h-5 w-5 -translate-y-1/2 text-slate-faint"
              aria-hidden="true"
            />
            <input
              id="locator-search"
              type="search"
              className="field-input pl-[2.75rem] pr-[3rem]"
              value={draft}
              maxLength={MAX_LOCATOR_SEARCH_LENGTH}
              placeholder="TSH-PC-0021, or plate compactor"
              autoComplete="off"
              onChange={(event) => setDraft(event.target.value)}
              aria-describedby="locator-search-help"
            />
            {draft.length > 0 && (
              <button
                type="button"
                onClick={() => setDraft('')}
                className="absolute right-xs top-1/2 flex h-11 w-11 -translate-y-1/2 cursor-pointer items-center justify-center rounded text-slate-soft transition-colors duration-200 hover:bg-muted hover:text-ink"
              >
                <X className="h-4 w-4" aria-hidden="true" />
                <span className="sr-only">Clear the search</span>
              </button>
            )}
          </div>
        </Field>
      </div>

      <UnitResults searched={searched} page={page} regionRef={resultsRef} onPage={goToPage} />
    </>
  )
}
