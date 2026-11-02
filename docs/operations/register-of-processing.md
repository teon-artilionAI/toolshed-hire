# Register of processing

Toolshed Hire, Task 3. Written on 23 October 2026 from the personal data map in
`backend/app/infrastructure/personal_data_map.py` and from the providers' own
published terms.

This register is a record of what the system actually does. It does not replace
the privacy notice a customer reads, and it does not claim a legal conclusion
that the operator terms do not support. Where a term is missing or narrower
than the deployment, the gap is written down rather than assumed away.

## 1. Responsible party and purpose

The responsible party is Teon Kleynhans, trading as the fictional Toolshed Hire
for the purposes of this university project. The system hires tagged tool and
equipment units from three Cape Town branches. It processes a customer's
details to open an account, take and confirm a booking, hand equipment over,
take it back, settle a deposit, record damage, report utilisation and gross
contribution, and meet the record-keeping duties that go with those actions.

The system is a demonstration. Every customer and hire in it is seeded or made
up, and no real customer data should be entered.

## 2. Data subjects and categories

The categories below are the ones the personal data map classifies. The map is
the source of truth, and its test fails when a table is added without a
classification.

| Category | Tables | What is held |
|---|---|---|
| Account and identity | `user_account`, `customer_profile` | Name, email address, phone number, role, password hash, identity document type and last four characters, billing address, account standing, trade discount, no-show and late-cancellation counts |
| Sessions and security | `refresh_session`, `audit_event` | Browser user agent, IP address, sign-in and lockout state, the actor and the before and after state of each recorded change |
| Bookings | `reservation`, `reservation_line`, `asset_allocation` | Branch, hire dates, status, prices copied at booking, notes and cancellation reason |
| Hires and money | `rental`, `rental_item`, `charge` | Collection and return, condition, meter readings, accessories, deposit held, withheld and refunded, balance, charge lines, waiver reasons and simulated payment references |
| Damage | `damage_report`, `damage_photo` | Description, severity, repair estimate and cost, resolution notes and the photographs |
| Notifications | `notification` | Recipient address, subject, delivery status and the provider's last error |

No special personal information is collected. The full identity number, card
details and bank details are never collected. The counter sees the document at
collection and only the last four characters are typed in.

## 3. Lawful processing basis

The POPIA section 11 basis for the account, booking, hire, deposit and damage
records is section 11(1)(b), because the processing is necessary to carry out
the hire agreement the customer enters into. The security records are processed
under section 11(1)(f), the legitimate interest in keeping the service and its
records secure, and the audit trail is also kept to meet the accountability
condition in section 8.

The transborder transfer basis recorded here is section 72(1)(a). Each operator
is bound by a data processing agreement or equivalent terms that provide an
adequate level of protection and that include terms on further transfers. The
alternative basis in section 72(1)(c), that the transfer is necessary for the
performance of the hire contract, also applies to the booking and hire records.

## 4. Operators

The table names each operator, what it holds, where it processes it, the term
that was read, and the date it was read. The region is the one this deployment
uses, not every region the operator offers.

| Operator | Service and data | Region used | Term and read date | Retention |
|---|---|---|---|---|
| Google Cloud (Google Cloud EMEA Limited and affiliates) | Cloud Run runs the API, Cloud Storage holds damage photographs, Secret Manager holds the application secrets, Artifact Registry holds the API image | `europe-west2` (London) | Cloud Data Processing Addendum, last modified 8 June 2026, read 23 October 2026. https://cloud.google.com/terms/data-processing-addendum | Photographs are deleted by the bucket lifecycle rule after five years. Cloud Run and Secret Manager data live while the project is active. |
| Neon, a Databricks company (Neon, LLC and Databricks, Inc.) | The PostgreSQL database, including every category above | AWS `eu-west-2` (London) | Product Specific Schedule (Neon), last updated 14 October 2026, under the Databricks Master Cloud Services Agreement and its Data Processing Addendum, read 23 October 2026. https://neon.com/dpa and https://www.databricks.com/legal/mcsa | Financial records five years. Personal details two years after the last hire unless the account is active. |
| Vercel Inc. | The React site, the `/api` function in front of Cloud Run, and the request logs and build artifacts that go with them | Function `lhr1` (London), with Vercel's edge and control plane elsewhere | Vercel Data Processing Addendum, last updated 17 March 2026, read 23 October 2026. https://vercel.com/legal/dpa | Provider logs follow the Hobby plan's retention. The application does not export them. |
| Resend (Plus Five Five, Inc.) | Booking confirmations, email verification and password reset messages, including the recipient address and the message text | Primary processing in the United States | Resend Data Processing Addendum, updated 31 December 2025, read 23 October 2026. https://resend.com/legal/dpa | Deleted within 90 days of account termination per the DPA. In restricted mode the only recipient is the owner address. |
| GitHub, Inc. | The public repository, issues, pull requests, Actions logs and uploaded artifacts | United States, with GitHub's subprocessors | GitHub Data Protection Agreement, read 23 October 2026. https://github.com/customer-terms/github-data-protection-agreement | Repository history is public and permanent. Actions artifacts are kept seven days by the workflows. |
| Have I Been Pwned (Superlative Enterprises Pty Ltd) | The first five characters of a password's SHA-1 digest, sent to the range API for a breach check. No account, address or identity is sent. | Superlative Enterprises Pty Ltd is based in Queensland, Australia. HIBP stores its data in a Microsoft Azure data centre in the western United States | HIBP Privacy Policy, updated May 2025, read 23 October 2026. https://haveibeenpwned.com/Privacy | The policy says no identifying information about who the password belongs to is stored. Operational logs are kept up to 31 days. |

GitHub is development tooling. It holds the repository, issues, pull requests
and continuous integration artifacts, not live customer data from the running
service. It is listed because a pipeline artifact can hold test data, which the
B14.3 scan checks before upload. It is not a service the public privacy notice
names as a handler of customer data.

The Google Cloud project, the Neon project, the Vercel projects, the Resend
account and the GitHub repository are all on the owner's own accounts. The
Google Cloud configuration is `toolshed` and the project is `toolshed-hire`.

## 5. Gaps and honest limits

These are written down because a register that hides them is worse than one
that names them.

- Vercel's DPA says on its face that it applies to Enterprise and Pro plans.
  This deployment is on the Hobby plan. The DPA text therefore does not, by
  itself, establish the section 72(1)(a) safeguard for Vercel. The transfer is
  still necessary for the hire service under section 72(1)(c), and Vercel's
  privacy policy and terms apply, but the gap is real and is recorded rather
  than papered over. The durable fix is a paid plan with the DPA in force, or
  moving the frontend to an operator whose DPA covers the plan used.
- Neon's published schedule now sits under Databricks' master agreement. The
  project was created before that change. The schedule and the Databricks DPA
  were read as the current terms, and the Neon subprocessor list includes
  Grafana Labs in the United States.
- HIBP receives a digest prefix, which the policy says cannot identify a
  person. It is listed as an operator because the call leaves the service.
  The application fails open if HIBP is unavailable, so the check is a
  security improvement and not a condition of using the system.
- Audit events are append-only and are not removed by the anonymiser. Their
  separate retention period has not been set. The financial record retention
  of five years is the longest period the system currently states.
- The privacy notice now names Neon, Google Cloud, Vercel, Resend and Have I
  Been Pwned, with the regions and the HIBP operator and storage location. The
  code change is PR #153.

## 6. How the system supports the rights

- Access. A customer downloads a statement and everything held about them from
  SC-09. The export is built from the personal data map, and credential columns
  are removed before the file is written.
- Correction. A customer edits their contact and billing details on SC-09. A
  branch corrects the rest.
- Deletion. A monthly Cloud Run job anonymises dormant customers, and an owner
  action anonymises a customer on request. Both keep the financial records and
  clear the identifying columns the map names.
- Objection and questions. The privacy notice gives the branch and the
  Information Regulator as the routes.

## 7. Sources read on 23 October 2026

- POPIA, Act 4 of 2013, sections 11 and 72. https://www.gov.za/documents/protection-personal-information-act and the section 72 text at https://www.acts.co.za/protection-of-personal-information-act/72__transfers_of_personal_info
- Google Cloud Data Processing Addendum. https://cloud.google.com/terms/data-processing-addendum
- Neon Product Specific Schedule. https://neon.com/dpa
- Databricks Master Cloud Services Agreement. https://www.databricks.com/legal/mcsa
- Vercel Data Processing Addendum. https://vercel.com/legal/dpa
- Resend Data Processing Addendum. https://resend.com/legal/dpa
- GitHub Data Protection Agreement. https://github.com/customer-terms/github-data-protection-agreement
- HIBP Privacy Policy. https://haveibeenpwned.com/Privacy
- The personal data map. `backend/app/infrastructure/personal_data_map.py`
- The privacy notice. `frontend/src/features/customer/PrivacyNotice.tsx`
