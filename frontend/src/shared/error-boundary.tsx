/**
 * The error boundary around every routed screen.
 *
 * A screen that throws while it renders would otherwise take the whole page
 * down and leave it blank. This catches the throw, keeps the shell and its
 * navigation on the page, and shows the shared error state in the screen's
 * place. A screen module that fails to download is caught the same way.
 *
 * The router gives each address its own boundary, so moving to another screen
 * always starts clean.
 */

import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { ErrorState } from './async-states'
import { PageHeader } from './ui'

interface BoundaryState {
  /** Null while the screen is rendering normally. */
  failure: { error: unknown } | null
}

export class ScreenErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { failure: null }

  static getDerivedStateFromError(error: unknown): BoundaryState {
    return { failure: { error } }
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // The person sees plain words. The detail goes to the console, where it is
    // useful, with the component stack that says which screen threw.
    console.error('ui.screen_render_failed', {
      event: 'ui.screen_render_failed',
      path: window.location.pathname,
      error_name: error instanceof Error ? error.name : typeof error,
      reason: error instanceof Error ? error.message : String(error),
      component_stack: info.componentStack,
    })
  }

  render(): ReactNode {
    const { failure } = this.state
    if (!failure) return this.props.children
    return (
      <>
        <PageHeader
          title="This screen could not be shown"
          subtitle="Nothing has been lost. Your bookings are safe."
        />
        <ErrorState
          what="this screen"
          error={failure.error}
          onRetry={() => this.setState({ failure: null })}
        >
          {/* A plain link to the same address. It makes the browser fetch the
              page again, which is the fix when a screen failed to download. */}
          <a href={window.location.href} className="btn-ghost px-md">
            Reload the page
          </a>
        </ErrorState>
      </>
    )
  }
}
