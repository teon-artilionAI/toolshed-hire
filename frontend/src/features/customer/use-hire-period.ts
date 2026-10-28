import { useEffect, useMemo, useRef, useState } from 'react'
import type { Branch } from '../../shared/api/contract'
import { closedDaysAt, closedEverywhere, openPeriod, type ClosedDays } from '../../shared/trading-days'
import { ANY_BRANCH } from './catalogue-ui'
import { DEFAULT_HIRE_DAYS, defaultPeriod, type HirePeriod } from './hire-period'

/**
 * The closed days that matter to a customer's dates. With no branch chosen a
 * day is closed only when every branch is, because another may serve.
 */
export function useClosedDays(branches: readonly Branch[] | undefined, branchCode: string): ClosedDays {
  return useMemo(
    () =>
      branchCode === ANY_BRANCH
        ? closedEverywhere(branches)
        : closedDaysAt(branches?.find((branch) => branch.code === branchCode)),
    [branches, branchCode],
  )
}

export interface HirePeriodState extends HirePeriod {
  setStartIso: (value: string) => void
  setEndIso: (value: string) => void
}

/**
 * The dates a screen's period fields hold.
 *
 * They open on today and four days on, or on the dates the address carried.
 * When the branches' closed days arrive, dates nobody chose that fall on a
 * closed day move to the next open days, once. Dates the customer typed or the
 * address carried are never moved, and a closed day the customer picks is
 * named by the validation instead.
 */
export function useHirePeriod(today: string, closed: ClosedDays, chosen?: HirePeriod): HirePeriodState {
  const [period, setPeriod] = useState<HirePeriod>(() => chosen ?? defaultPeriod(today))
  const settled = useRef(chosen !== undefined)

  useEffect(() => {
    if (settled.current || closed.size === 0) return
    settled.current = true
    setPeriod((current) =>
      closed.has(current.startIso) || closed.has(current.endIso)
        ? openPeriod(current.startIso, DEFAULT_HIRE_DAYS, closed)
        : current,
    )
  }, [closed])

  return {
    ...period,
    setStartIso: (value) => {
      settled.current = true
      setPeriod((current) => ({ ...current, startIso: value }))
    },
    setEndIso: (value) => {
      settled.current = true
      setPeriod((current) => ({ ...current, endIso: value }))
    },
  }
}
