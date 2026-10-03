/**
 * SC-12 Customer Lookup and Walk-in Registration.
 *
 * Almost every counter conversation starts here, and it starts with a phone
 * number read out over a counter. So there is one search box, and the API
 * matches what is typed against the name, the phone number and the email
 * address at once. It searches from two characters, a moment after the last
 * key, so it never runs on every keystroke.
 *
 * The search, the page and the chosen customer live in the address, so a
 * reload brings the same screen back and the next screen can send a person
 * back to it. A query string is user input, so a page the screen cannot offer
 * falls back to the first.
 *
 * A customer who is not on file yet is registered on the same screen and not
 * somewhere else, because the queue does not pause while an assistant
 * navigates. Once they are registered they are chosen, and their booking is
 * one press away.
 *
 * The branch the assistant works at comes from work-branch.ts, through the
 * gate. It decides where a walk in is registered and which bookings can go
 * out over this counter.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Search, UserPlus, X } from 'lucide-react'
import type { CustomerSummary } from '../../shared/api/contract'
import { MAX_CUSTOMER_SEARCH_LENGTH, MIN_CUSTOMER_SEARCH_LENGTH } from '../../shared/api/customers'
import { Field, PageHeader } from '../../shared/ui'
import { CUSTOMER_PARAMETER } from './counter-links'
import { ChosenCustomer } from './SC12-Customer-Bookings'
import { FIRST_PAGE, SearchResults } from './SC12-Search-Results'
import WalkinForm from './SC12-Walkin-Form'
import { useWorkBranch } from './work-branch'
import { WorkBranchGate } from './work-branch-gate'
import type { CounterBranch } from './work-branch-gate'

/** How long the search waits after the last key before it runs. */
const SEARCH_DEBOUNCE_MS = 300

const QUERY_PARAMETER = 'q'
const PAGE_PARAMETER = 'page'

function readPage(value: string | null): number {
  const page = Number.parseInt(value ?? '', 10)
  return Number.isInteger(page) && page >= FIRST_PAGE ? page : FIRST_PAGE
}

interface LookupAddress {
  q: string
  page: number
  customer: string | null
}

function LookupDesk({ branch }: { branch: CounterBranch }) {
  const { chooses } = useWorkBranch()
  const [params, setParams] = useSearchParams()
  const searched = (params.get(QUERY_PARAMETER) ?? '').trim()
  const page = readPage(params.get(PAGE_PARAMETER))
  const chosenId = params.get(CUSTOMER_PARAMETER)
  const nameInputRef = useRef<HTMLInputElement>(null)
  const resultsRef = useRef<HTMLElement>(null)
  const [focusRequest, setFocusRequest] = useState(0)
  const [registeredId, setRegisteredId] = useState<string | null>(null)

  /** Write the search, the page and the customer to the address. A default is left out. */
  const show = useCallback(
    (next: LookupAddress) => {
      const written = new URLSearchParams()
      if (next.q) written.set(QUERY_PARAMETER, next.q)
      if (next.page > FIRST_PAGE) written.set(PAGE_PARAMETER, String(next.page))
      if (next.customer) written.set(CUSTOMER_PARAMETER, next.customer)
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
    const timer = window.setTimeout(
      () => show({ q: typed, page: FIRST_PAGE, customer: chosenId }),
      SEARCH_DEBOUNCE_MS,
    )
    return () => window.clearTimeout(timer)
  }, [draft, searched, chosenId, show])

  function choose(customer: CustomerSummary) {
    setRegisteredId(null)
    setFocusRequest((count) => count + 1)
    show({ q: searched, page, customer: customer.id })
  }

  function goToPage(next: number) {
    show({ q: searched, page: next, customer: chosenId })
    // The new page replaces the list, so focus goes to the top of it and a
    // keyboard user reads the new page from its first customer.
    resultsRef.current?.focus()
  }

  /** A browser scrolls a box into view when it takes focus, so focus is enough. */
  function focusRegistration() {
    nameInputRef.current?.focus()
  }

  return (
    <>
      <div className="mb-lg flex flex-wrap items-end gap-md">
        <div className="min-w-[16rem] max-w-xl flex-1">
          <Field
            label="Search customers"
            htmlFor="customer-search"
            help={`A name, a mobile number or an email address. ${MIN_CUSTOMER_SEARCH_LENGTH} characters or more.`}
          >
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-md top-1/2 h-5 w-5 -translate-y-1/2 text-slate-faint"
                aria-hidden="true"
              />
              <input
                id="customer-search"
                type="search"
                className="field-input pl-[2.75rem] pr-[3rem]"
                value={draft}
                maxLength={MAX_CUSTOMER_SEARCH_LENGTH}
                placeholder="082 441 7719"
                autoComplete="off"
                onChange={(event) => setDraft(event.target.value)}
                aria-describedby="customer-search-help"
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
        <button type="button" onClick={focusRegistration} className="btn-secondary px-md">
          <UserPlus className="h-4 w-4 shrink-0" aria-hidden="true" />
          Register a walk in
        </button>
      </div>

      <SearchResults
        searched={searched}
        page={page}
        regionRef={resultsRef}
        onPage={goToPage}
        onChoose={choose}
        onRegister={focusRegistration}
      />

      {chosenId !== null && (
        <div className="mb-lg">
          <ChosenCustomer
            key={chosenId}
            customerId={chosenId}
            branch={branch}
            focusRequest={focusRequest}
            justRegistered={registeredId === chosenId}
          />
        </div>
      )}

      <WalkinForm
        branchCode={chooses ? branch.code : null}
        branchName={branch.name}
        nameInputRef={nameInputRef}
        onRegistered={(customer) => {
          setRegisteredId(customer.id)
          setFocusRequest((count) => count + 1)
          show({ q: searched, page, customer: customer.id })
        }}
      />
    </>
  )
}

export default function CustomerLookup() {
  return (
    <>
      <PageHeader
        screenId="SC-12"
        title="Find a customer"
        subtitle="Search by name, mobile number or email. If they are not on file, register them as a walk in below and carry on."
      />
      <WorkBranchGate>{(branch) => <LookupDesk branch={branch} />}</WorkBranchGate>
    </>
  )
}
