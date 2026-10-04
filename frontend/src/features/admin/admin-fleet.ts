/**
 * The groups of unit states the admin screens on sample data still use.
 *
 * SC-20 and SC-21 read the fixtures until a later change connects them, and
 * they sort units by these two groups. The fleet arithmetic that used to live
 * here, the positions, the utilisation and the overdue exposure of each
 * branch, is gone. SC-19 now shows the figures the server sends and works
 * none out.
 */

import type { AssetStatus } from '../../shared/types'

/** A unit that is off the road earns nothing and cannot be hired out. */
export const OFF_ROAD: AssetStatus[] = ['QUARANTINED', 'MAINTENANCE']
/** Retired and lost units have left the fleet, so they do not drag utilisation down. */
export const OUT_OF_FLEET: AssetStatus[] = ['RETIRED', 'LOST']
