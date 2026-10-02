/**
 * Tests for the shared loading and error states, the error boundary and the
 * page controls.
 *
 * I check what a person or a screen reader is told. In particular I check what
 * a person is not told, because the error state must never leak the raw error.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './api-problem'
import type { ApiFailureKind } from './api-problem'
import { ErrorState, LoadingState } from './async-states'
import { ScreenErrorBoundary } from './error-boundary'
import Pagination from './pagination'

function failure(kind: ApiFailureKind, status: number | null, requestId: string | null): ApiError {
  return new ApiError({
    kind,
    status,
    title: 'Internal Server Error',
    detail: '/api/catalogue/models answered 500 without a problem document.',
    requestPath: '/api/catalogue/models',
    requestId,
  })
}

describe('LoadingState', () => {
  it('marks the region as busy and announces what is loading', () => {
    const { container } = render(<LoadingState label="Loading the catalogue" />)

    expect(screen.getByRole('status')).toHaveTextContent('Loading the catalogue')
    expect(container.firstElementChild).toHaveAttribute('aria-busy', 'true')
  })

  it('draws as many blocks as it is asked for and hides them from a screen reader', () => {
    const { container } = render(<LoadingState label="Loading" shape="cards" count={6} />)

    const skeleton = container.querySelector('[aria-hidden="true"]')
    expect(skeleton?.children).toHaveLength(6)
  })
})

describe('ErrorState', () => {
  it('says what failed in plain words, as an alert', () => {
    render(<ErrorState what="the catalogue" error={failure('problem', 500, 'req-42')} />)

    const alert = screen.getByRole('alert')
    expect(within(alert).getByText('We could not load the catalogue')).toBeVisible()
    expect(within(alert).getByText(/Something went wrong on our side/)).toBeVisible()
  })

  it('takes a whole heading for an action that failed, where nothing was being loaded', () => {
    render(<ErrorState heading="We could not sign you in" error={failure('transport', null, null)} />)

    expect(screen.getByRole('alert')).toHaveTextContent('We could not sign you in')
    expect(screen.getByRole('alert')).not.toHaveTextContent('We could not load')
  })

  it('tells a person to check their connection when the API was not reached', () => {
    render(<ErrorState what="the catalogue" error={failure('transport', null, null)} />)

    expect(screen.getByRole('alert')).toHaveTextContent(/Check your connection and try again/)
  })

  it('shows the request id so it can be quoted', () => {
    render(<ErrorState what="the catalogue" error={failure('problem', 500, 'req-42-abc')} />)

    expect(screen.getByText('req-42-abc')).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent(/Reference to quote/)
  })

  it('shows no reference line when the request never reached the server', () => {
    render(<ErrorState what="the catalogue" error={failure('transport', null, null)} />)

    expect(screen.getByRole('alert')).not.toHaveTextContent(/Reference/)
  })

  it('never shows the raw error text, the path or the status code', () => {
    render(<ErrorState what="the catalogue" error={failure('problem', 500, 'req-42')} />)

    const alert = screen.getByRole('alert')
    expect(alert).not.toHaveTextContent('Internal Server Error')
    expect(alert).not.toHaveTextContent('/api/')
    expect(alert).not.toHaveTextContent('500')
    expect(alert).not.toHaveTextContent('problem document')
  })

  it('never shows the message of an error that did not come from the API', () => {
    render(<ErrorState what="this screen" error={new TypeError('x.map is not a function')} />)

    expect(screen.getByRole('alert')).not.toHaveTextContent('x.map')
    expect(screen.getByRole('alert')).toHaveTextContent('We could not load this screen')
  })

  it('offers a retry and calls back when it is pressed', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<ErrorState what="the catalogue" error={failure('gateway', 502, null)} onRetry={onRetry} />)

    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('has no retry button when trying again is not on offer', () => {
    render(<ErrorState what="the catalogue" error={failure('problem', 500, null)} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('ScreenErrorBoundary', () => {
  function Unstable({ broken }: { broken: { now: boolean } }) {
    if (broken.now) throw new Error('Cannot read properties of undefined (reading "items")')
    return <p>The screen is showing</p>
  }

  it('shows the error state in place of a screen that throws', () => {
    // React and the boundary both report the throw. I keep it out of the run.
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ScreenErrorBoundary>
        <Unstable broken={{ now: true }} />
      </ScreenErrorBoundary>,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'This screen could not be shown' })).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('We could not load this screen')
    expect(screen.getByRole('alert')).not.toHaveTextContent('Cannot read properties')
    expect(screen.getByRole('link', { name: 'Reload the page' })).toBeVisible()
  })

  it('shows the screen again when the retry works', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    const broken = { now: true }
    render(
      <ScreenErrorBoundary>
        <Unstable broken={broken} />
      </ScreenErrorBoundary>,
    )

    broken.now = false
    await user.click(screen.getByRole('button', { name: 'Try again' }))

    expect(screen.getByText('The screen is showing')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('leaves a working screen alone', () => {
    render(
      <ScreenErrorBoundary>
        <Unstable broken={{ now: false }} />
      </ScreenErrorBoundary>,
    )

    expect(screen.getByText('The screen is showing')).toBeVisible()
  })
})

describe('Pagination', () => {
  it('is a named landmark that announces the current page', () => {
    render(<Pagination label="Search result pages" page={2} pageSize={24} total={60} onPageChange={() => {}} />)

    const nav = screen.getByRole('navigation', { name: 'Search result pages' })
    expect(within(nav).getByRole('status')).toHaveTextContent('Page 2 of 3')
    expect(within(nav).getByRole('button', { name: 'Page 2' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('button', { name: 'Page 1' })).not.toHaveAttribute('aria-current')
  })

  it('moves a page forward and back', async () => {
    const user = userEvent.setup()
    const onPageChange = vi.fn()
    render(<Pagination label="Pages" page={2} pageSize={24} total={60} onPageChange={onPageChange} />)

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    await user.click(screen.getByRole('button', { name: 'Page 3' }))

    expect(onPageChange.mock.calls).toEqual([[3], [1], [3]])
  })

  it('cannot go before the first page or past the last', () => {
    const { rerender } = render(
      <Pagination label="Pages" page={1} pageSize={24} total={60} onPageChange={() => {}} />,
    )
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()

    rerender(<Pagination label="Pages" page={3} pageSize={24} total={60} onPageChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('leaves out the middle of a long run but keeps the first and last page', () => {
    render(<Pagination label="Pages" page={5} pageSize={10} total={200} onPageChange={() => {}} />)

    const numbered = screen
      .getAllByRole('button', { name: /^Page \d+$/ })
      .map((button) => button.textContent)
    expect(numbered).toEqual(['1', '4', '5', '6', '20'])
  })

  it('draws nothing when everything fits on one page', () => {
    const { container } = render(
      <Pagination label="Pages" page={1} pageSize={24} total={24} onPageChange={() => {}} />,
    )

    expect(container).toBeEmptyDOMElement()
  })
})
