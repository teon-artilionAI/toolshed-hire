/**
 * The branch a counter screen works at, before the screen itself.
 *
 * Counter staff go straight through, with the branch on their account. An
 * administrator is asked which branch they are working at, once for the tab,
 * and then goes through with that one. A line at the top says which branch it
 * is and offers to change it, because an administrator may cover any of them.
 *
 * The branches offered are the ones the API lists. The name of a branch comes
 * from the same list, and its code stands in until the list arrives.
 */

import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapPin } from 'lucide-react'
import { catalogueQueries } from '../../shared/api/catalogue-queries'
import { queryPhase } from '../../shared/api/query-phase'
import { ErrorState, LoadingState } from '../../shared/async-states'
import { Card, Notice } from '../../shared/ui'
import { useWorkBranch } from './work-branch'

/** The branch a screen works at, with the name a person reads. */
export interface CounterBranch {
  code: string
  name: string
}

export function WorkBranchGate({ children }: { children: (branch: CounterBranch) => ReactNode }) {
  const { code, chooses, choose, forget } = useWorkBranch()
  const branches = useQuery(catalogueQueries.branches())
  const phase = queryPhase(branches)
  const list = branches.data?.items ?? []
  const known = list.find((branch) => branch.code === code)

  if (!chooses) {
    if (code === null) {
      return (
        <Notice tone="error" title="Your account has no branch">
          <p>
            A counter account works at one branch, and this one names none. Ask an administrator
            to set your branch, then sign in again.
          </p>
        </Notice>
      )
    }
    return <>{children({ code, name: known?.name ?? `Branch ${code}` })}</>
  }

  if (phase === 'loading' || phase === 'idle') {
    return <LoadingState label="Loading the branches" shape="tiles" />
  }
  if (phase === 'failed') {
    return <ErrorState what="the branches" error={branches.error} onRetry={() => void branches.refetch()} />
  }

  if (known === undefined) {
    return (
      <Card title="Which branch are you working at?">
        <p className="mb-md text-sm text-slate-soft">
          Your account is not tied to one branch. Choose the counter you are standing at. Bookings
          and walk ins are made there, and this tab remembers it until you close it.
        </p>
        <ul className="grid gap-sm sm:grid-cols-3">
          {list.map((branch) => (
            <li key={branch.code}>
              <button
                type="button"
                className="btn-secondary w-full justify-start px-md py-md text-base"
                onClick={() => choose(branch.code)}
              >
                <MapPin className="h-5 w-5 shrink-0" aria-hidden="true" />
                <span>
                  {branch.name}
                  <span className="block text-sm text-slate-soft">{branch.suburb}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>
    )
  }

  return (
    <>
      <div className="mb-lg flex flex-wrap items-center gap-sm rounded border border-line bg-surface px-md py-sm">
        <MapPin className="h-5 w-5 shrink-0 text-slate-faint" aria-hidden="true" />
        <p role="status" className="text-sm text-ink">
          You are working at <span className="font-semibold">{known.name}</span> in this tab.
        </p>
        <button type="button" className="btn-ghost ml-auto px-md" onClick={forget}>
          Change branch
        </button>
      </div>
      {children({ code: known.code, name: known.name })}
    </>
  )
}
