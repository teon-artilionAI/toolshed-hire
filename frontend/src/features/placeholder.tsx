/**
 * Stand-in for a screen that has not been written yet.
 *
 * The router wires all twenty four screens from the outset so the
 * navigation is real and the inventory reconciles. A screen whose module
 * does not exist yet renders this instead of breaking the build, and it
 * says so plainly rather than pretending to be finished work.
 *
 * Delete nothing here. Each screen simply stops using it the moment its
 * own module lands at the path the router expects.
 */

import { Construction } from 'lucide-react'
import type { ScreenDef } from '../shared/navigation'
import { ROLE_LABEL } from '../shared/navigation'
import { PageHeader } from '../shared/ui'

export default function Placeholder({ screen }: { screen: ScreenDef }) {
  return (
    <>
      <PageHeader
        screenId={screen.id}
        title={screen.name}
        subtitle={`A ${ROLE_LABEL[screen.role].toLowerCase()} screen.`}
      />
      <div className="card border-dashed p-lg">
        <div className="flex items-start gap-md">
          <Construction
            className="mt-0.5 h-6 w-6 shrink-0 text-slate-faint"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-ink">
              This screen is not built yet
            </h2>
            <p className="mt-xs text-sm text-slate-soft">
              {screen.id} {screen.name} is in the screen inventory and its
              address works, so you can reach it from the navigation. The
              content arrives with the rest of this build.
            </p>
            <p className="mt-md font-mono text-xs text-slate-faint">
              {screen.path}
            </p>
          </div>
        </div>
      </div>
    </>
  )
}
