/**
 * The wire types, all of them, in one place.
 *
 * Every type that mirrors a body the API sends or a query it accepts is
 * exported from here, and the application imports a wire type from nowhere
 * else. The shapes are not written by hand. They come from schema.d.ts, which
 * `npm run api:types` generates from the OpenAPI document the backend commits.
 * When the backend changes a route, a field or a query parameter, the
 * generated file changes with it, and whatever in the application no longer
 * fits stops compiling.
 *
 * The generated file is read through contract-kit.ts, which also holds the
 * type tools used below. Its names follow the backend's class and function
 * names, and a screen should not have to know those. The branch and catalogue
 * types are in contract-catalogue.ts, the reservation types are in
 * contract-booking.ts, the registration and account types are in
 * contract-account.ts, the counter types are in contract-counter.ts, the
 * counter overview types are in contract-overview.ts, the returns and
 * settlement types are in contract-returns.ts, the damage and quarantine
 * types are in contract-damage.ts, the reporting types are in
 * contract-reporting.ts, the admin operations types are in
 * contract-operations.ts, the admin catalogue types are in
 * contract-admin-catalogue.ts, the asset register types are in
 * contract-admin-assets.ts, and the staff account and customer hold types are
 * in contract-admin-users.ts. All twelve are passed on from here, and the
 * session types below stay here. The last of them is written by hand until
 * the generated schema describes its routes, and its header says why.
 *
 * Where the generated type says less than the screens rely on, I keep a more
 * precise type here and say why beside it. A refinement can only name a member
 * the generated type has, and can only narrow it. So a member the backend
 * renames, removes or retypes is still a compile error here.
 *
 * This file holds types only. A runtime value such as a page size limit lives
 * beside the endpoint that uses it, because generated types carry no values.
 */

import type { BodyOf, JsonOf, Paths, Refine, Schemas } from './contract-kit'

export type { ClockTime, IsoDate, IsoTimestamp, Money } from './contract-kit'
export type {
  AvailabilityPage,
  AvailabilityQuery,
  Branch,
  BranchAvailability,
  BranchList,
  Category,
  CategoryList,
  ModelAvailability,
  ModelAvailabilityQuery,
  ModelAvailabilityRow,
  ModelDetail,
  ModelListQuery,
  ModelPage,
  ModelQuote,
  ModelQuoteQuery,
  ModelSort,
  ModelSummary,
  QuoteBasis,
  UnitQuote,
} from './contract-catalogue'
export type {
  AccountStatus,
  CompletePasswordResetRequest,
  CustomerType,
  EmailDelivery,
  IdDocumentType,
  MyProfile,
  PasswordResetRequest,
  RegisterRequest,
  UpdateMyProfileRequest,
  VerifyEmailRequest,
} from './contract-account'
export type {
  CancelReservationRequest,
  CreateReservationRequest,
  Reservation,
  ReservationLine,
  ReservationLineRequest,
  ReservationListQuery,
  ReservationPage,
  ReservationStatus,
} from './contract-booking'
export type {
  ChargeStatus,
  ChargeType,
  CheckoutCustomer,
  CheckoutItemRequest,
  CheckoutRequest,
  CheckoutUnit,
  ConditionGrade,
  CustomerPage,
  CustomerSearchQuery,
  CustomerSummary,
  DamageAssessment,
  RegisterWalkInRequest,
  Rental,
  RentalCharge,
  RentalItem,
  RentalStatus,
  ReservationCheckout,
  SettlementWaitingOn,
} from './contract-counter'
export type {
  AssetStatus,
  BranchDiary,
  CounterDashboard,
  DashboardCollection,
  DashboardCounts,
  DashboardOverdue,
  DashboardQuery,
  DashboardReturn,
  DiaryCollection,
  DiaryCollectionStatus,
  DiaryDay,
  DiaryQuery,
  DiaryReturn,
  LocatedUnit,
  LocatorPage,
  LocatorQuery,
  NoShowRequest,
} from './contract-overview'
export type {
  DamageOutcome,
  DamageReport,
  DamageReportListQuery,
  DamageReportPage,
  DamageSeverity,
  DamageStatus,
  FileDamageReportRequest,
  ResolveDamageReportRequest,
} from './contract-damage'
export type {
  BalancePaymentRequest,
  MyRentalsQuery,
  RentalListQuery,
  RentalPage,
  ReturnItemRequest,
  ReturnRequest,
} from './contract-returns'
export type {
  AdminDashboard,
  DashboardBranch,
  FleetCounts,
  MonthToDate,
  Percent,
  ReportDefinitions,
  ReportFigures,
  ReportGrouping,
  ReportRow,
  UtilisationCsvQuery,
  UtilisationReport,
  UtilisationReportQuery,
} from './contract-reporting'
export type {
  AuditActorRole,
  AuditEvent,
  AuditEventPage,
  AuditEventQuery,
  AuditState,
  CorrectionReasonRequest,
  EmailNotification,
  EmailNotificationPage,
  EmailNotificationQuery,
  HireAdjustmentRequest,
  NotificationStatus,
  NotificationType,
} from './contract-operations'
export type {
  AdminCategory,
  AdminCategoryList,
  AdminCategoryQuery,
  AdminModel,
  AdminModelPage,
  AdminModelQuery,
  CategoryChangesRequest,
  ModelChangesRequest,
  NewCategoryRequest,
  NewModelRequest,
  PublicationRequest,
} from './contract-admin-catalogue'
export type {
  AdminAsset,
  AdminAssetDetail,
  AdminAssetPage,
  AdminAssetQuery,
  AssetChangesRequest,
  AssetHistoryEntry,
  AssetHistoryKind,
  AssetTransitionRequest,
  NewAssetRequest,
} from './contract-admin-assets'
export type {
  AdminCustomerQuery,
  AdminUser,
  AdminUserPage,
  AdminUserQuery,
  CustomerStandingRequest,
  DeactivationRequest,
  NewStaffAccountRequest,
  StaffAccountChangesRequest,
  StaffAccountCreated,
  StaffRole,
} from './contract-admin-users'

/**
 * An RFC 9457 problem document, as the backend's `ProblemDetail` emits it.
 *
 * The API may send null for the three optional members. The client leaves a
 * null one out when it reads the document, so here each is present or absent
 * and never null.
 *
 * `errors` says more about the refusal. On a 422 it holds one member,
 * `fields`, and that holds a sentence for each refused value. Each name there
 * starts with where the value came from, for example `query.to` or
 * `body.email`. On a 404 it names what was looked for. problem-fields.ts turns
 * the 422 shape into a lookup by the bare field name.
 */
export type ProblemDocument = Refine<
  Schemas['ProblemDetail'],
  {
    instance?: string
    errors?: Record<string, unknown>
    /** The same value as the `X-Request-ID` response header. */
    requestId?: string
  }
>

/** The roles the backend maps its stored roles onto. The generated type is a
 *  plain `string`, and the screens branch on the role, so I keep the union. */
export type UserRole = 'customer' | 'counter' | 'admin'

/** What `GET /api/health` reports about its own dependencies. */
export type HealthReport = JsonOf<Paths['/api/health']['get']>

/**
 * The signed in account. `GET /api/me`, and the `user` member of what login
 * and refresh answer with.
 *
 * Counter staff carry the code of the branch they work at. Customers and
 * administrators do not, and `branchCode` is null for them. Null is a fact
 * about the role and not missing data. The generated type also lets the member
 * be left out. The reader in auth.ts turns a missing one into null, so here it
 * is always present.
 */
export type SessionUser = Refine<
  JsonOf<Paths['/api/me']['get']>,
  { role: UserRole; branchCode: string | null }
>

/** The body `POST /api/auth/login` accepts. */
export type LoginRequest = BodyOf<Paths['/api/auth/login']['post']>

/** The one token type the API issues. The generated type is a plain `string`,
 *  and the client only knows how to send this one. */
export type AccessTokenType = 'Bearer'

/**
 * What `POST /api/auth/login` and `POST /api/auth/refresh` both answer with.
 *
 * The access token, how many seconds it lasts, and whom it belongs to. The
 * refresh token is not here. The server keeps it in an HttpOnly cookie that
 * the page cannot read.
 *
 * `POST /api/auth/logout` takes no body and answers 204 with none, so it needs
 * no type here.
 */
export type SessionGrant = Refine<
  JsonOf<Paths['/api/auth/login']['post']> & JsonOf<Paths['/api/auth/refresh']['post']>,
  { tokenType: AccessTokenType; user: SessionUser }
>
