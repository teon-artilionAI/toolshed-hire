/**
 * What the SC-11 test files share.
 *
 * The diary reads the session for the branch the assistant works at, so it is
 * opened inside the whole application, the way a person reaches it. The routes
 * are set, the screen is opened, and the tests read the page.
 */

import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import type { DiaryDay } from '../../shared/api/contract'
import { jsonResponse, mockApi } from '../../test/api-mock'
import type { ApiMock, RouteHandler, RouteTable } from '../../test/api-mock'
import { DIARY_ROUTE, diaryOf, emptyDay } from '../../test/overview-samples'
import { findScreenHeading, renderApp } from '../../test/render-app'
import { COUNTER_STAFF, signedInAs } from '../../test/session-samples'
import { addDays } from './diary-dates'

export const HEADING = 'Branch diary'

/** Open SC-11 as counter staff at Bellville, on the address given. */
export async function openDiary(routes: RouteTable, at = '/counter/diary'): Promise<{ user: UserEvent; network: ApiMock }> {
  const network = mockApi({ ...signedInAs(COUNTER_STAFF), ...routes })
  renderApp(at)
  await findScreenHeading(HEADING)
  return { user: userEvent.setup(), network }
}

/**
 * The diary route the way the server answers it. Every day asked for is
 * there, in order, and the days named in `filled` carry what they hold.
 */
export function diaryAnswering(filled: readonly DiaryDay[] = []): RouteHandler {
  return (request) => {
    const from = request.query.get('from') ?? ''
    const count = Number(request.query.get('days') ?? '1')
    const days = Array.from({ length: count }, (_, index) => {
      const date = addDays(from, index)
      return filled.find((day) => day.date === date) ?? emptyDay(date)
    })
    return jsonResponse(diaryOf(days))
  }
}

/** The query of the last diary request, as `from` and `days`. */
export function lastDiaryAsked(network: ApiMock): string {
  const asked = network.requestsTo(DIARY_ROUTE).at(-1)?.query
  return `${asked?.get('from') ?? ''} for ${asked?.get('days') ?? ''}`
}
