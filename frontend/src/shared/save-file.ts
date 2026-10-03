/**
 * Hands the browser a file to save, under the name it should have.
 *
 * A file the API sends with a token cannot be fetched by a plain link, because
 * a link goes out with no token. So the client fetches it, and this gives the
 * bytes to the browser through a temporary address and a link that is pressed
 * once and taken away again. The bytes are saved exactly as they arrived.
 *
 * The temporary address holds the file in memory until it is released. It is
 * released a while after the press and not at once, because some browsers
 * start reading it only after the press has returned, and a file released too
 * early is saved empty.
 */

import { logEvent } from './api/log'

/** How long the temporary address is kept after the press. */
const TEMPORARY_ADDRESS_LIFETIME_MS = 40_000

/** A file to save, with the name to save it under. */
export interface FileToSave {
  fileName: string
  content: Blob
}

/**
 * Ask the browser to save a file.
 *
 * @param file The bytes and the name. The name is used as it is, so it must
 *   already be a plain file name.
 */
export function saveFile(file: FileToSave): void {
  const address = URL.createObjectURL(file.content)
  const link = document.createElement('a')
  link.href = address
  link.download = file.fileName
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(address), TEMPORARY_ADDRESS_LIFETIME_MS)
  logEvent('info', 'file.saved', { file_name: file.fileName, bytes: file.content.size })
}
