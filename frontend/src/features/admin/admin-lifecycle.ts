/**
 * The asset lifecycle, written down once.
 *
 * A unit does not go from any state to any other state. It cannot be
 * retired while a customer is holding it, it cannot go back on the shelf
 * with a damage report still open against it, and once it is retired it
 * stays retired. Offering every status from every status would make the
 * register look powerful and let a branch quietly lose a tool.
 *
 * Used by SC-21.
 */

import type { AssetStatus } from '../../shared/types'

/** Every status a unit can hold, in the order it tends to move through them. */
export const ALL_STATUSES: AssetStatus[] = [
  'AVAILABLE', 'RESERVED', 'ON_HIRE', 'QUARANTINED', 'MAINTENANCE', 'RETIRED', 'LOST',
]

export interface LifecycleMove {
  to: AssetStatus
  /** What the person is doing, in their words. */
  label: string
  /** What happens as a result. */
  consequence: string
}

/**
 * What each status may move to from the asset register. Returns and
 * collections are not here on purpose: those belong to the counter, and
 * duplicating them in the back office is how two systems start to disagree.
 */
export const LIFECYCLE: Record<AssetStatus, LifecycleMove[]> = {
  AVAILABLE: [
    { to: 'MAINTENANCE', label: 'Book it in for a service', consequence: 'Comes off the shelf and stops being offered to customers.' },
    { to: 'QUARANTINED', label: 'Quarantine it', consequence: 'Held back pending inspection. Nobody can hire it.' },
    { to: 'RETIRED', label: 'Retire it', consequence: 'Leaves the fleet for good and stops counting towards utilisation.' },
    { to: 'LOST', label: 'Report it lost', consequence: 'Recorded as lost at its replacement value.' },
  ],
  RESERVED: [
    { to: 'AVAILABLE', label: 'Release the hold', consequence: 'Frees the unit for other bookings. The booking keeps its place in the diary.' },
    { to: 'QUARANTINED', label: 'Quarantine it', consequence: 'Held back pending inspection. The booking will need another unit.' },
  ],
  ON_HIRE: [
    { to: 'LOST', label: 'Report it lost', consequence: 'For kit a customer cannot return. Recorded at its replacement value.' },
  ],
  QUARANTINED: [
    { to: 'MAINTENANCE', label: 'Send it for repair', consequence: 'Moves to the workshop queue.' },
    { to: 'AVAILABLE', label: 'Put it back on the shelf', consequence: 'Back in the fleet and offered to customers again.' },
    { to: 'RETIRED', label: 'Write it off', consequence: 'Beyond economical repair. Leaves the fleet at its replacement value.' },
    { to: 'LOST', label: 'Report it lost', consequence: 'Recorded as lost at its replacement value.' },
  ],
  MAINTENANCE: [
    { to: 'AVAILABLE', label: 'Repair finished, back on the shelf', consequence: 'Back in the fleet and offered to customers again.' },
    { to: 'QUARANTINED', label: 'Hold it back', consequence: 'Repair did not settle it. Held pending a decision.' },
    { to: 'RETIRED', label: 'Write it off', consequence: 'Beyond economical repair. Leaves the fleet at its replacement value.' },
  ],
  RETIRED: [],
  LOST: [
    { to: 'QUARANTINED', label: 'It has turned up', consequence: 'Comes back for inspection before it goes near a customer.' },
  ],
}

/** Moves that change money or liability, so they need a written reason. */
export const NEEDS_REASON: AssetStatus[] = ['QUARANTINED', 'RETIRED', 'LOST']

/** Moves that take the unit out of the fleet and cannot be walked back. */
export const LEAVES_THE_FLEET: AssetStatus[] = ['RETIRED', 'LOST']

/**
 * Why a move that is otherwise legal cannot be made right now, or null if
 * it can. The message says what to do about it, not just what is wrong.
 */
export function blockedReason(move: LifecycleMove, hasOpenDamage: boolean): string | null {
  if (move.to === 'AVAILABLE' && hasOpenDamage) {
    return 'Resolve the damage report first, with the repair cost, and this unit can go back on the shelf.'
  }
  return null
}

/** Why there is nothing to do from this status, for the empty case. */
export function noMovesReason(status: AssetStatus): string {
  if (status === 'RETIRED') {
    return 'This unit has left the fleet. Retirement is final, so there is nothing further to change here.'
  }
  return `There is nothing to change from ${status.toLowerCase().replace('_', ' ')} on this screen.`
}
