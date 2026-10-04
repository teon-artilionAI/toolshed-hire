/**
 * The wire types of the owner's staff accounts and customer holds.
 *
 * They are built from the generated schema the way every other wire type is,
 * so a route, a field or a value the backend changes stops the application
 * compiling until it follows. They live apart from contract.ts only to keep
 * each file a size that can be read in one sitting.
 *
 * The generated types say less than the server does in three ways, and the
 * types below say it exactly. The generated role is any stored role, and the
 * server only ever lists, opens or moves a staff account, so here the role is
 * one of the two staff roles. The generated body of a change lets the name and
 * the role be null, and the server refuses null for both naming the field,
 * because every staff account has them. So here each is a value or left out.
 * And the generated query and new account body let some members be left out
 * that the screen always sends, so here those are required.
 *
 * A customer on the holds reads as the same `CustomerSummary` the counter
 * uses. The two types below that say so are built from the owner's own routes,
 * so if those ever answer with something other than what the counter reads,
 * this file stops compiling.
 *
 * Nothing imports this file but contract.ts. The application imports these
 * types from there, like every other wire type.
 */

import type { CustomerSummary } from './contract-counter'
import type {
  BodyOf,
  CreatedJsonOf,
  IsoTimestamp,
  JsonOf,
  Paths,
  QueryOf,
  Refine,
  Schemas,
} from './contract-kit'

type UsersRoute = Paths['/api/admin/users']
type UserRoute = Paths['/api/admin/users/{id}']
type DeactivationRoute = Paths['/api/admin/users/{id}/deactivation']
type ReactivationRoute = Paths['/api/admin/users/{id}/reactivation']
type CustomersRoute = Paths['/api/admin/customers']
type CustomerStatusRoute = Paths['/api/admin/customers/{id}/status']

/** The two roles a staff account can hold, as the API writes them. */
export type StaffRole = Exclude<Schemas['UserRole'], 'CUSTOMER'>

/**
 * One staff account as the owner reads it. `AdminUser` in the contract.
 *
 * `branchCode` names the branch of a member of counter staff and is null for
 * an administrator, who works across every branch. `phone` is null when none
 * was given. `isActive` is false once the account has been deactivated, and a
 * deactivated account cannot sign in. `emailVerified` is true once the person
 * has proved the address. `lastLoginAt` is null for somebody who has never
 * signed in, and `lockedUntil` is the end of a lock after too many failed
 * sign ins, or null. Nothing about a password is ever sent.
 *
 * The list, a new account, a change, a deactivation and a reactivation all
 * answer with an account this way, so it is built from all five.
 */
export type AdminUser = Refine<
  JsonOf<UsersRoute['get']>['items'][number] &
    CreatedJsonOf<UsersRoute['post']>['user'] &
    JsonOf<UserRoute['patch']> &
    JsonOf<DeactivationRoute['post']> &
    JsonOf<ReactivationRoute['post']>,
  {
    role: StaffRole
    lastLoginAt: IsoTimestamp | null
    lockedUntil: IsoTimestamp | null
    createdAt: IsoTimestamp
  }
>

/**
 * The query `GET /api/admin/users` accepts.
 *
 * `q` is part of a name or an email address, two to eighty characters once
 * trimmed. `role` narrows the list to one role, and `active` to the accounts
 * that can sign in or to those that cannot. Every filter may be left out. The
 * generated type lets the role be a customer's, which the server refuses with
 * a 422 naming `role`, and lets the page and its size be left out, which the
 * screen always sends. So here the role is a staff role and both are required.
 */
export type AdminUserQuery = Refine<
  QueryOf<UsersRoute['get']>,
  { role?: StaffRole; page: number; pageSize: number }
>

/** `GET /api/admin/users`. One page of the staff and admin accounts, by name. */
export type AdminUserPage = Refine<JsonOf<UsersRoute['get']>, { items: AdminUser[] }>

/**
 * The body `POST /api/admin/users` accepts. Exactly these five members, and
 * never a password.
 *
 * `branchCode` is required for counter staff and must be null for an
 * administrator, each refused with a 422 naming `branchCode`. `phone` is null
 * when none is given. An address another account already has is refused with
 * a 422 naming `email`. The generated type lets the phone and the branch be
 * left out, and the screen always sends both, null for none, so here they are
 * required.
 */
export type NewStaffAccountRequest = Refine<
  BodyOf<UsersRoute['post']>,
  { phone: string | null; role: StaffRole; branchCode: string | null }
>

/**
 * What `POST /api/admin/users` answers with, `201`. The new account, and
 * whether the link to choose a password was taken by the email gateway. When
 * `emailDeliverable` is false the link never left the system, so the person
 * cannot sign in until email is set up and they ask for a new link.
 */
export type StaffAccountCreated = Refine<CreatedJsonOf<UsersRoute['post']>, { user: AdminUser }>

/**
 * The body `PATCH /api/admin/users/{id}` accepts. Any of the name, the phone,
 * the role and the branch, and only what changed. A field left out keeps its
 * value. Null clears the phone, and the branch is null for an administrator.
 * Making somebody an administrator without naming a branch lets go of the
 * branch they had. The address is not among them, and the server refuses a
 * body that names it. Moving the last active administrator to another role is
 * a 409.
 */
export type StaffAccountChangesRequest = Refine<
  BodyOf<UserRoute['patch']>,
  { fullName?: string; role?: StaffRole }
>

/**
 * The body `POST /api/admin/users/{id}/deactivation` accepts. The reason is
 * kept with the audit event. Deactivating the last active administrator, or
 * one's own account, is a 409. Deactivation also withdraws a reset link the
 * person has not used yet.
 */
export type DeactivationRequest = BodyOf<DeactivationRoute['post']>

/**
 * The query `GET /api/admin/customers` accepts. `status` narrows the list to
 * one standing and `q` matches a name, a phone number or an email address.
 * Both may be left out. The generated type lets the page and its size be left
 * out, and the screen always sends both, so here they are required.
 */
export type AdminCustomerQuery = Refine<QueryOf<CustomersRoute['get']>, { page: number; pageSize: number }>

/** `GET /api/admin/customers`. One page of the customers that match, by name. */
export type AdminCustomerPage = Refine<JsonOf<CustomersRoute['get']>, { items: CustomerSummary[] }>

/**
 * The body `POST /api/admin/customers/{id}/status` accepts. The standing to
 * move the customer to, and why. Releasing a hold leaves the count of
 * bookings the customer did not collect as it is. Asking for the standing a
 * customer already has changes nothing.
 */
export type CustomerStandingRequest = BodyOf<CustomerStatusRoute['post']>

/** What `POST /api/admin/customers/{id}/status` answers with. The customer as
 *  they now stand, read as the counter reads a customer. */
export type CustomerWithStanding = Refine<JsonOf<CustomerStatusRoute['post']>, CustomerSummary>
