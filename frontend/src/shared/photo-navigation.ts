/**
 * Opens a signed link to a damage photograph.
 *
 * The link is on Cloud Storage, which serves the photograph as a download, so
 * sending this window to it saves the photograph and leaves the page where it
 * is. It is a navigation and not a request, so the content security policy,
 * which keeps every request and every image on this origin, never has to be
 * widened for it, and no byte of a photograph is drawn on the page.
 *
 * It does not open a new window. The link is only known once the API has
 * answered, and a browser blocks a window opened that long after the press as
 * a popup.
 *
 * It is one object with one method so a test can watch it.
 */

import { logEvent } from './api/log'

export const photoNavigation = {
  /** Send the window to the link. Only an https address is ever passed here. */
  open(url: string): void {
    logEvent('info', 'file.photo_opened', { host: new URL(url).host })
    window.location.assign(url)
  },
}
