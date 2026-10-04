/**
 * The groups of unit states the asset register on sample data still uses.
 *
 * SC-21 reads the fixtures until a later change connects it, and it sorts
 * units by these two groups. The fleet arithmetic that used to live here, the
 * positions, the utilisation and the overdue exposure of each branch, is
 * gone. SC-19 now shows the figures the server sends and works none out, and
 * SC-20 shows the count of units the server sends for each model.
 */

import type { AssetStatus } from '../../shared/types'

/** A unit that is off the road earns nothing and cannot be hired out. */
export const OFF_ROAD: AssetStatus[] = ['QUARANTINED', 'MAINTENANCE']
/** Retired and lost units have left the fleet, so they do not drag utilisation down. */
export const OUT_OF_FLEET: AssetStatus[] = ['RETIRED', 'LOST']
