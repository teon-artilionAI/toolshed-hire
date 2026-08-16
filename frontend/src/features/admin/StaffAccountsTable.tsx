/**
 * The staff table on SC-23, with its own filters.
 *
 * Role and branch are edited in place with real select controls rather than
 * behind a modal, because changing somebody's branch is a one second job and
 * a dialogue for it is three clicks of ceremony. Each control carries a
 * screen reader label naming the person it belongs to, so a keyboard user
 * always knows whose row they are in.
 */

import { useMemo, useState } from 'react'
import { Power, PowerOff } from 'lucide-react'
import { branches } from '../../shared/fixtures'
import type { BranchCode, Role, UserAccount } from '../../shared/types'
import { DataTable, EmptyState, Field, StatusPill } from '../../shared/ui'

const SELECT_CLASS =
  'field-input min-w-[9rem] cursor-pointer transition-colors duration-200'

type RoleFilter = 'ALL' | 'counter' | 'admin'
type StatusFilter = 'ALL' | 'active' | 'inactive'

export default function StaffAccountsTable({
  staff,
  signedInUserId,
  onChangeRole,
  onChangeBranch,
  onToggleActive,
}: {
  staff: UserAccount[]
  signedInUserId?: string
  onChangeRole: (account: UserAccount, role: Role) => void
  onChangeBranch: (account: UserAccount, branchCode?: BranchCode) => void
  onToggleActive: (account: UserAccount) => void
}) {
  const [query, setQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('ALL')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL')

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return staff.filter(
      (a) =>
        (needle === '' ||
          a.name.toLowerCase().includes(needle) ||
          a.email.toLowerCase().includes(needle)) &&
        (roleFilter === 'ALL' || a.role === roleFilter) &&
        (statusFilter === 'ALL' ||
          (statusFilter === 'active' ? a.active : !a.active)),
    )
  }, [staff, query, roleFilter, statusFilter])

  function showEverybody() {
    setQuery('')
    setRoleFilter('ALL')
    setStatusFilter('ALL')
  }

  return (
    <>
      <div className="mb-lg grid gap-md sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Search by name or email" htmlFor="staff-search">
          <input
            id="staff-search"
            type="search"
            className="field-input"
            placeholder="Elmarie, or thabo@"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </Field>
        <Field label="Role" htmlFor="staff-role-filter">
          <select
            id="staff-role-filter"
            className={SELECT_CLASS}
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value as RoleFilter)}
          >
            <option value="ALL">Every role</option>
            <option value="counter">Counter staff</option>
            <option value="admin">Admin and owner</option>
          </select>
        </Field>
        <Field label="Can they sign in?" htmlFor="staff-status-filter">
          <select
            id="staff-status-filter"
            className={SELECT_CLASS}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          >
            <option value="ALL">Both</option>
            <option value="active">Yes, active</option>
            <option value="inactive">No, switched off</option>
          </select>
        </Field>
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title="No staff account matches that"
          body="Clear the search or widen the role and status filters to see the rest of the team."
          action={
            <button type="button" className="btn-secondary px-md" onClick={showEverybody}>
              Show everybody
            </button>
          }
        />
      ) : (
        <DataTable
          columns={['Name', 'Role', 'Branch', 'Can sign in', 'Action']}
          caption="Staff accounts, their roles and their branches"
        >
          {shown.map((account) => (
            <tr
              key={account.id}
              className="transition-colors duration-200 hover:bg-muted"
            >
              <th scope="row" className="td text-left font-medium text-ink">
                {account.name}
                {account.id === signedInUserId && (
                  <span className="ml-sm text-xs font-normal text-slate-soft">
                    (you)
                  </span>
                )}
                <span className="mt-xs block text-xs font-normal text-slate-soft">
                  {account.email}
                </span>
              </th>
              <td className="td">
                <label className="sr-only" htmlFor={`role-${account.id}`}>
                  Role for {account.name}
                </label>
                <select
                  id={`role-${account.id}`}
                  className={SELECT_CLASS}
                  value={account.role}
                  onChange={(e) => onChangeRole(account, e.target.value as Role)}
                >
                  <option value="counter">Counter staff</option>
                  <option value="admin">Admin and owner</option>
                </select>
              </td>
              <td className="td">
                <label className="sr-only" htmlFor={`branch-${account.id}`}>
                  Branch for {account.name}
                </label>
                <select
                  id={`branch-${account.id}`}
                  className={SELECT_CLASS}
                  value={account.branchCode ?? ''}
                  onChange={(e) =>
                    onChangeBranch(
                      account,
                      (e.target.value || undefined) as BranchCode | undefined,
                    )
                  }
                >
                  <option value="">All three branches</option>
                  {branches.map((b) => (
                    <option key={b.code} value={b.code}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </td>
              <td className="td">
                {account.active ? (
                  <StatusPill status="AVAILABLE" label="Yes, active" />
                ) : (
                  <StatusPill status="RETIRED" label="No, switched off" />
                )}
              </td>
              <td className="td">
                <button
                  type="button"
                  className={account.active ? 'btn-secondary px-md' : 'btn-primary px-md'}
                  onClick={() => onToggleActive(account)}
                >
                  {account.active ? (
                    <PowerOff className="h-4 w-4 shrink-0" aria-hidden="true" />
                  ) : (
                    <Power className="h-4 w-4 shrink-0" aria-hidden="true" />
                  )}
                  {account.active ? 'Switch off' : 'Switch back on'}
                </button>
              </td>
            </tr>
          ))}
        </DataTable>
      )}
    </>
  )
}
