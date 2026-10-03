/**
 * INFO-01 Privacy Notice.
 *
 * What Toolshed Hire collects about a customer, why, who handles it and what
 * the customer can do about it, in plain words. It is public, because a
 * visitor has to be able to read it before they register. The registration
 * form links here beside its acceptance box, and the shell links here from
 * the footer of every screen.
 *
 * It is a supporting page and not one of the numbered screens, so it carries
 * an identifier outside the SC series and shows none in its header.
 *
 * The page holds words only. It reads nothing from the API and keeps nothing.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CATALOGUE_PATH } from '../../shared/navigation'
import { Notice, PageHeader } from '../../shared/ui'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-lg">
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-sm flex flex-col gap-sm text-sm text-ink">{children}</div>
    </section>
  )
}

function Points({ children }: { children: ReactNode }) {
  return <ul className="flex list-disc flex-col gap-xs pl-lg">{children}</ul>
}

export default function PrivacyNotice() {
  return (
    <>
      <PageHeader
        title="Privacy notice"
        subtitle="What we collect about you, why we collect it, who handles it and what you can do about it."
      />

      <div className="mx-auto w-full max-w-2xl">
        <Notice tone="warn" title="Do not enter real personal information">
          <p>
            Toolshed Hire is a fictional business, built as a university project. Nothing here is
            a real hire, so please use made up details.
          </p>
        </Notice>

        <div className="card mt-lg px-lg pb-lg">
          <Section title="Who is responsible">
            <p>
              Toolshed Hire is responsible for the information this system holds. It is a
              fictional tool and equipment hire business with three branches in Cape Town, built
              as a university project.
            </p>
          </Section>

          <Section title="What we collect and why">
            <Points>
              <li>
                Your account and contact details, which are your name, email address, mobile
                number, billing address and password. We use them to make and confirm your
                bookings and to reach you about a hire. The password is stored as a hash, which
                cannot be read back.
              </li>
              <li>
                The type of your identity document and the last four characters of its number.
                The counter uses them to check that the person collecting equipment is the
                person who booked it.
              </li>
              <li>
                Your hire and charge history, which is what you booked, what you collected and
                returned, and what was charged. We keep it so that a deposit and any fee can be
                accounted for.
              </li>
            </Points>
          </Section>

          <Section title="What we never collect">
            <Points>
              <li>
                Your full identity number, passport number or licence number. The counter looks
                at the document when you collect and nothing more than the last four characters
                is typed in.
              </li>
              <li>Card details or bank details.</li>
            </Points>
          </Section>

          <Section title="Who handles it and where">
            <Points>
              <li>The database is held by Neon in London, in the United Kingdom.</li>
              <li>The service that answers the website runs on Google Cloud in London.</li>
              <li>The website itself is served by Vercel.</li>
              <li>Email is sent through Resend.</li>
            </Points>
            <p>Each of them handles the information only to run this system for us.</p>
          </Section>

          <Section title="Marketing">
            <p>
              Nothing you give us is used for marketing. The only email we send is about your
              own account and your own bookings.
            </p>
          </Section>

          <Section title="How long we keep it">
            <p>
              The period we keep information for is not fixed yet. It will be stated here before
              this system is used for real customers.
            </p>
          </Section>

          <Section title="Your rights">
            <p>
              You may ask to see the information we hold about you, ask us to correct it, and
              object to how we use it. You can see and correct your contact and billing details
              yourself on your account screen. For anything else, ask at any branch.
            </p>
          </Section>

          <Section title="If you want to complain">
            <p>
              If you are not satisfied with how your information is handled, you can complain to
              the Information Regulator of South Africa.
            </p>
          </Section>
        </div>

        <Link to={CATALOGUE_PATH} className="btn-secondary mt-lg px-md">
          Back to the catalogue
        </Link>
      </div>
    </>
  )
}
