/**
 * The notice above every screen that is not connected to the API yet.
 *
 * The screens were connected one group at a time, and every numbered screen
 * reads from the API now, so the notice shows nowhere today. It stays for a
 * screen added later, which must not pass made up data off as real before it
 * is connected. Whether it shows is decided by the `live` flag of the screen
 * in navigation.ts and by nothing else. Connecting a screen means changing
 * that flag, and the notice goes without anyone touching the screen or this
 * file.
 *
 * The outer element is a status region that stays on the page whether or not
 * there is anything in it. A screen reader announces a change inside a region
 * it already knows about, and is far less dependable about a region that
 * appears already filled. It sits in the normal flow above the screen, so it
 * pushes the content down and never lies on top of it.
 */

import { FlaskConical } from 'lucide-react'
import type { ScreenDef } from './navigation'

export const SAMPLE_DATA_TITLE = 'This screen still shows sample data'

/**
 * @param screen The screen being shown, or undefined when the shell is showing
 *   something that is not a screen from the inventory, such as a refusal.
 */
export function SampleDataNotice({ screen }: { screen: ScreenDef | undefined }) {
  const showsSampleData = screen !== undefined && !screen.live
  return (
    <div role="status">
      {showsSampleData && (
        <div className="mb-lg flex items-start gap-sm rounded-lg border-2 border-status-due bg-status-due-wash px-md py-md">
          <FlaskConical className="mt-0.5 h-5 w-5 shrink-0 text-status-due" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-base font-semibold text-ink">{SAMPLE_DATA_TITLE}</p>
            <p className="mt-xs text-sm text-ink">
              It is being connected to the live system. The names, bookings and figures below are
              examples, and nothing you change here is saved.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
