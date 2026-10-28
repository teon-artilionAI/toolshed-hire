/**
 * The design's week for a branch, Monday to Friday 07:00 to 17:00 and Saturday
 * 07:00 to 13:00, as `GET /api/branches` sends it. Shared by the mocked answers
 * so each branch they describe trades the way a real one does.
 */
export const STANDARD_WEEK = [1, 2, 3, 4, 5].map((weekday) => ({ weekday, opensAt: '07:00', closesAt: '17:00' })).concat([
  { weekday: 6, opensAt: '07:00', closesAt: '13:00' },
])

/** An ordinary trading day at the counter, as the dashboard and the diary send it. */
export const OPEN_DAY = {
  open: true,
  opensAt: '07:00',
  closesAt: '17:00',
  closedReason: null,
  closedKind: null,
}
