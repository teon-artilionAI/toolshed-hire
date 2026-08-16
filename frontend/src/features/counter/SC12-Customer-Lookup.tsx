/**
 * SC-12 Customer Lookup and Walk-in Registration.
 *
 * Almost every counter conversation starts here, and it starts with a
 * phone number read out over a counter. So there is one search box, it
 * matches on number, name or email at once, and it filters as you type. A
 * customer who is not on file yet is registered on the same screen rather
 * than somewhere else, because the queue does not pause while you navigate.
 */

import { useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, X } from 'lucide-react'
import {
  Card,
  DataTable,
  EmptyState,
  Field,
  Notice,
  PageHeader,
  StatusPill,
} from '../../shared/ui'
import { customers } from '../../shared/fixtures'
import { formatDate } from '../../shared/format'
import type { CustomerProfile } from '../../shared/types'
import WalkinForm from './SC12-Walkin-Form'

const COLUMNS = ['Customer', 'Mobile', 'Email', 'Account', 'Action']

function digitsOnly(value: string): string {
  return value.replace(/\D/g, '')
}

/** One box, three ways in. A counter assistant should never have to decide
 *  which field they are searching before they start typing. */
function matches(customer: CustomerProfile, query: string): boolean {
  const trimmed = query.trim().toLowerCase()
  if (trimmed.length === 0) return true
  const asDigits = digitsOnly(trimmed)
  if (asDigits.length >= 3 && digitsOnly(customer.phone).includes(asDigits)) return true
  return (
    customer.name.toLowerCase().includes(trimmed) ||
    customer.email.toLowerCase().includes(trimmed)
  )
}

export default function CustomerLookup() {
  const [query, setQuery] = useState('')
  const [added, setAdded] = useState<CustomerProfile[]>([])
  const [justAdded, setJustAdded] = useState<CustomerProfile | null>(null)
  const nameInputRef = useRef<HTMLInputElement>(null)

  const everyone = useMemo(() => [...added, ...customers], [added])
  const results = useMemo(
    () => everyone.filter((customer) => matches(customer, query)),
    [everyone, query],
  )

  function focusRegistration() {
    nameInputRef.current?.focus()
    nameInputRef.current?.scrollIntoView({ block: 'center' })
  }

  return (
    <div>
      <PageHeader
        screenId="SC-12"
        title="Find a customer"
        subtitle="Search by mobile number, name or email. If they are not on file, register them here and carry on."
        actions={
          <button type="button" onClick={focusRegistration} className="btn-secondary">
            Register a walk-in
          </button>
        }
      />

      {justAdded && (
        <div className="mb-lg">
          <Notice tone="success" title={`${justAdded.name} is on file`}>
            <p>
              Added today on {justAdded.phone}. You can start their booking straight away.
            </p>
            <Link to="/counter/booking" className="btn-primary mt-sm">
              Start a booking for {justAdded.name}
            </Link>
          </Notice>
        </div>
      )}

      <div className="mb-lg max-w-xl">
        <Field
          label="Search customers"
          htmlFor="customer-search"
          help="Part of a number, name or email is enough."
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
              value={query}
              placeholder="082 441 7719"
              autoComplete="off"
              onChange={(event) => setQuery(event.target.value)}
              aria-describedby="customer-search-help"
            />
            {query.length > 0 && (
              <button
                type="button"
                onClick={() => setQuery('')}
                className="absolute right-xs top-1/2 flex h-11 w-11 -translate-y-1/2 cursor-pointer items-center justify-center rounded text-slate-soft transition-colors duration-200 hover:bg-muted hover:text-ink"
              >
                <X className="h-4 w-4" aria-hidden="true" />
                <span className="sr-only">Clear the search</span>
              </button>
            )}
          </div>
        </Field>
      </div>

      <Card
        title={
          query.trim().length === 0
            ? `All customers, ${results.length}`
            : `${results.length} ${results.length === 1 ? 'match' : 'matches'}`
        }
        className="mb-lg"
      >
        {results.length === 0 ? (
          <EmptyState
            title="Nobody on file matches that"
            body="Check the number for a typo, or register them as a walk-in and carry on with the hire."
            action={
              <button type="button" onClick={focusRegistration} className="btn-primary">
                Register a walk-in
              </button>
            }
          />
        ) : (
          <DataTable caption="Customers matching the search" columns={COLUMNS}>
            {results.map((customer) => (
              <tr key={customer.id}>
                <td className="td">
                  <span className="font-medium text-ink">{customer.name}</span>
                  <span className="block text-xs text-slate-soft">
                    {customer.billingSuburb}, on file since {formatDate(customer.joinedOn)}
                  </span>
                </td>
                <td className="td whitespace-nowrap font-mono tabular">{customer.phone}</td>
                <td className="td break-all">
                  {customer.email || <span className="text-slate-soft">No email on file</span>}
                </td>
                <td className="td">
                  {customer.onHold ? (
                    <StatusPill status="OVERDUE" label="Account on hold" />
                  ) : (
                    <StatusPill status="AVAILABLE" label="Good standing" />
                  )}
                </td>
                <td className="td">
                  {customer.onHold ? (
                    <span className="text-sm text-status-overdue">
                      Cannot hire until an owner lifts the hold
                    </span>
                  ) : (
                    <Link to="/counter/booking" className="btn-secondary whitespace-nowrap">
                      Start a booking
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </DataTable>
        )}
      </Card>

      <WalkinForm
        existing={everyone}
        nameInputRef={nameInputRef}
        onRegistered={(customer) => {
          setAdded((current) => [customer, ...current])
          setJustAdded(customer)
          setQuery(customer.phone)
          window.scrollTo({ top: 0 })
        }}
      />
    </div>
  )
}
