/**
 * The heading of a state a screen has just changed to.
 *
 * When a form is replaced by its answer, the button the person pressed is no
 * longer on the page. Focus would be left on nothing, and a screen reader
 * would say nothing. This heading takes focus as it appears, so the new state
 * is read out from its first words and a keyboard carries on from there.
 */

import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

export function StateHeading({ children }: { children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  return (
    <h2 ref={heading} tabIndex={-1} className="text-xl font-semibold text-ink">
      {children}
    </h2>
  )
}
