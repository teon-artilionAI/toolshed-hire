/**
 * Domain types for the Toolshed Hire prototype.
 *
 * These mirror the entities and enumerations in the Task 1 canonical model
 * so that the prototype, the ERD and the design class diagram describe one
 * system. Where a name differs from the documentation, the documentation is
 * wrong and should be corrected rather than the type renamed.
 *
 * The prototype has no back end. Data comes from fixtures and mutations are
 * held in memory, which is what Task 1 asks for: design and interaction,
 * with dummy data, and no back end coding required.
 */

export type Uuid = string

/** The three branches. Matches Branch.code in the canonical model. */
export type BranchCode = 'CBD' | 'BEL' | 'SOM'

export interface Branch {
  id: Uuid
  code: BranchCode
  name: string
  suburb: string
}

export type Role = 'customer' | 'counter' | 'admin'

export interface UserAccount {
  id: Uuid
  name: string
  email: string
  role: Role
  branchCode?: BranchCode
  active: boolean
}

/** Condition grades recorded at checkout and return. A is best. */
export type ConditionGrade = 'A' | 'B' | 'C' | 'D'

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

export interface Category {
  id: Uuid
  name: string
  slug: string
}

/** A catalogue entry. Roughly 120 of these across 400 physical assets. */
export interface ProductModel {
  id: Uuid
  categoryId: Uuid
  name: string
  manufacturer: string
  sku: string
  description: string
  /** Daily hire rate in rand. Stored as a number here; NUMERIC in the schema. */
  dailyRate: number
  depositAmount: number
  lateFeePerDay: number
  replacementValue: number
  published: boolean
  imageTone: string
}

/** An individually tagged physical unit, for example TSH-DR-0042. */
export interface Asset {
  id: Uuid
  productModelId: Uuid
  tag: string
  branchCode: BranchCode
  status: AssetStatus
  condition: ConditionGrade
  acquiredOn: string
  acquisitionCost: number
  meterHours?: number
}

export interface ReservationLine {
  id: Uuid
  productModelId: Uuid
  quantity: number
  /** Rate captured when the booking was made, so later price changes do not
   *  rewrite history. */
  ratePerDaySnapshot: number
  depositPerUnitSnapshot: number
  allocatedAssetIds: Uuid[]
}

export interface Reservation {
  id: Uuid
  reference: string
  customerId: Uuid
  branchCode: BranchCode
  status: ReservationStatus
  /** Half open period. A return on the 12th frees the 12th. */
  startDate: string
  endDate: string
  lines: ReservationLine[]
  createdAt: string
  notes?: string
}

export interface RentalItem {
  id: Uuid
  assetId: Uuid
  conditionOut: ConditionGrade
  conditionIn?: ConditionGrade
  returnedAt?: string
  meterOut?: number
  meterIn?: number
}

export interface Rental {
  id: Uuid
  reference: string
  reservationId: Uuid
  customerId: Uuid
  branchCode: BranchCode
  status: RentalStatus
  collectedAt: string
  dueBackOn: string
  depositHeld: number
  items: RentalItem[]
}

export type ChargeKind =
  | 'HIRE'
  | 'DEPOSIT'
  | 'LATE_FEE'
  | 'DAMAGE'
  | 'REFUND'

export interface Charge {
  id: Uuid
  rentalId: Uuid
  kind: ChargeKind
  amount: number
  description: string
  settled: boolean
  raisedAt: string
}

export interface DamageReport {
  id: Uuid
  assetId: Uuid
  rentalId: Uuid
  status: DamageStatus
  severity: 'MINOR' | 'MODERATE' | 'SEVERE'
  description: string
  estimatedRepairCost: number
  actualRepairCost?: number
  chargeable: boolean
  raisedAt: string
}

export interface CustomerProfile {
  id: Uuid
  userId?: Uuid
  name: string
  email: string
  phone: string
  idDocType: 'SA_ID' | 'PASSPORT' | 'DRIVING_LICENCE'
  idDocNumber: string
  billingSuburb: string
  billingCity: string
  onHold: boolean
  joinedOn: string
}

export interface AuditEvent {
  id: Uuid
  at: string
  actor: string
  action: string
  entity: string
  detail: string
}

export interface NotificationRecord {
  id: Uuid
  at: string
  to: string
  kind: 'BOOKING_CONFIRMATION'
  reference: string
  delivered: boolean
}

/** Availability of one product model at one branch over a period. */
export interface AvailabilityResult {
  productModelId: Uuid
  branchCode: BranchCode
  availableUnits: number
  totalUnits: number
}
