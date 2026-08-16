/**
 * Turning an availability count into a sentence a customer can act on.
 *
 * Kept apart from the arithmetic because it is wording, not maths, and
 * because getting it wrong is how a system starts lying politely. An
 * overdue unit is also a unit out on hire, so it is described once and not
 * counted twice in the sentence; a retired unit is not "in the workshop",
 * it is gone.
 */

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`
}

export interface ShortfallReason {
  fleetUnits: number
  /** Quarantined or in maintenance, so expected back eventually. */
  workshopUnits: number
  /** Retired or lost, so never coming back. */
  withdrawnUnits: number
  outUnits: number
  bookedUnits: number
  overdueUnits: number
  availableUnits: number
}

/** A sentence, or null when the whole fleet at this branch is free. */
export function reasonFor(input: ShortfallReason): string | null {
  if (input.fleetUnits === 0) return 'Not kept at this branch'
  if (input.availableUnits === input.fleetUnits) return null

  const parts: string[] = []
  const outOnTime = Math.max(0, input.outUnits - input.overdueUnits)
  if (outOnTime > 0) {
    parts.push(`${plural(outOnTime, 'unit is', 'units are')} out on hire`)
  }
  if (input.overdueUnits > 0) {
    parts.push(
      `${plural(input.overdueUnits, 'unit is', 'units are')} out on hire and overdue with no return date yet`,
    )
  }
  if (input.bookedUnits > 0) {
    parts.push(`${plural(input.bookedUnits, 'unit is', 'units are')} booked for these dates`)
  }
  if (input.workshopUnits > 0) {
    parts.push(`${plural(input.workshopUnits, 'unit is', 'units are')} in the workshop`)
  }
  if (input.withdrawnUnits > 0) {
    parts.push(
      `${plural(input.withdrawnUnits, 'unit has', 'units have')} been taken out of service`,
    )
  }

  if (parts.length === 0) return null
  const sentence =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`
  return sentence.charAt(0).toUpperCase() + sentence.slice(1)
}
