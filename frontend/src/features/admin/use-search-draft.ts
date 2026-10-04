/**
 * A search box whose words reach the address a moment after the last key.
 *
 * The box holds what is being typed and the address holds what was last
 * searched. The search asks a moment after the last key, so it never asks the
 * server on every keystroke, and when the address changes from somewhere else
 * the box follows it. The wait is cleared whenever the words change again or
 * the box leaves the page, so nothing is left running.
 */

import { useEffect, useState } from 'react'

/** How long the search waits after the last key before it asks. */
export const SEARCH_DEBOUNCE_MS = 300

/**
 * @param searched What the address says was last searched, or null for nothing.
 * @param onSearch Called with the words once typing stops, or null when the box
 *   was emptied. It should be stable between renders.
 * @returns The words in the box and the way to change them.
 */
export function useSearchDraft(searched: string | null, onSearch: (words: string | null) => void): [string, (typed: string) => void] {
  const inAddress = searched ?? ''
  const [draft, setDraft] = useState(inAddress)
  const [lastSearched, setLastSearched] = useState(inAddress)
  if (inAddress !== lastSearched) {
    setLastSearched(inAddress)
    if (inAddress !== draft.trim()) setDraft(inAddress)
  }
  useEffect(() => {
    const typed = draft.trim()
    if (typed === inAddress) return
    const timer = window.setTimeout(() => onSearch(typed === '' ? null : typed), SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [draft, inAddress, onSearch])
  return [draft, setDraft]
}
