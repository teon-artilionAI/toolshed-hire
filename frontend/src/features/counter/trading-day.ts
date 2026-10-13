/**
 * How the counter's screens put whether the branch trades on a day into words.
 *
 * The server decides from the branch's weekly hours, the public holidays and
 * the owner's closure days, and sends the day's hours or why it is closed. The
 * dashboard and the diary say the same thing the same way through these.
 */

import type { TradingDay } from '../../shared/api/contract'

/** The hours of an open day, for example "Open 07:00 to 13:00". */
export function openingHoursText(trading: TradingDay): string | null {
  if (!trading.open || trading.opensAt === null || trading.closesAt === null) return null
  return `Open ${trading.opensAt} to ${trading.closesAt}`
}

/**
 * Why the branch is closed on a day, as a short phrase, or null when it is open.
 * A weekly closing reads "Closed on Sundays", and a holiday or a closure day
 * reads "Closed for Christmas Day" or "Closed for stocktake".
 */
export function closedText(trading: TradingDay): string | null {
  if (trading.open || trading.closedReason === null) return null
  if (trading.closedKind === 'weekly') {
    return `Closed${trading.closedReason.replace(/^is closed/, '')}`
  }
  return `Closed for ${trading.closedReason}`
}
