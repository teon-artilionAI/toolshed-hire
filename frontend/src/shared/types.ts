/**
 * The few types the shell and the status pill still take from the prototype.
 *
 * Every screen reads from the API now, and the wire types in api/contract.ts
 * describe what each one shows. What is left here is the role the screen
 * inventory, the guards and the session speak of, and the status words the
 * status pill accepts. The sample data and the entity types that described it
 * went with the last screen that read it.
 */

export type Role = 'customer' | 'counter' | 'admin'

export type AssetStatus =
  | 'AVAILABLE'
  | 'RESERVED'
  | 'ON_HIRE'
  | 'QUARANTINED'
  | 'MAINTENANCE'
  | 'RETIRED'
  | 'LOST'

export type ReservationStatus =
  | 'DRAFT'
  | 'HELD'
  | 'CONFIRMED'
  | 'COLLECTED'
  | 'CLOSED'
  | 'CANCELLED'
  | 'NO_SHOW'
  | 'EXPIRED'

export type RentalStatus =
  | 'OPEN'
  | 'OVERDUE'
  | 'PARTIALLY_RETURNED'
  | 'RETURNED'
  | 'SETTLED'

export type DamageStatus = 'OPEN' | 'UNDER_REPAIR' | 'RESOLVED'
