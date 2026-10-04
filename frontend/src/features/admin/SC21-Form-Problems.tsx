/**
 * What is wrong with a form of SC-21, above it, after a press that was held
 * back or refused.
 *
 * Each problem links to the field it is about. A message the server sent
 * about a field the form has no box for is listed with them, and a refusal
 * that named no field at all shows the server's sentence. The notice can take
 * focus, so the person is told at once that nothing was saved and why.
 */

import type { Ref } from 'react'
import { Notice } from '../../shared/ui'
import { ProblemList } from '../counter/counter-fields'

export function FormProblems({
  ref,
  problems,
  leftOver,
  detail = null,
}: {
  ref: Ref<HTMLDivElement>
  /** One for each field with a message, in the order of the form. */
  problems: readonly { id: string; message: string }[]
  /** The server's messages about fields the form has no box for. */
  leftOver: readonly string[]
  /** The server's sentence for a refusal that named no field, or null. */
  detail?: string | null
}) {
  const count = problems.length + leftOver.length
  if (count === 0 && detail === null) return null
  return (
    <div ref={ref} tabIndex={-1} className="mb-md">
      <Notice
        tone="error"
        title={
          count === 0
            ? 'Nothing has been saved yet.'
            : `Nothing has been saved yet. ${count} ${count === 1 ? 'answer needs' : 'answers need'} fixing.`
        }
      >
        {count === 0 && detail !== null && <p>{detail}</p>}
        <ProblemList problems={problems} />
        {leftOver.length > 0 && (
          <ul className="mt-xs list-disc pl-lg">
            {leftOver.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        )}
      </Notice>
    </div>
  )
}
