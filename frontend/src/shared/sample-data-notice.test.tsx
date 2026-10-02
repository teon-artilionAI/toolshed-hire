/**
 * Tests for the notice above a screen that still shows sample data.
 *
 * The notice is driven by the `live` flag in the screen inventory and by
 * nothing else. These tests flip the flag on a copy of a screen and check the
 * notice follows it, and they pin which screens the inventory calls live, so
 * connecting a screen is a deliberate change to one flag and to one line here.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SCREENS, screenById } from './navigation'
import type { ScreenDef } from './navigation'
import { SAMPLE_DATA_TITLE, SampleDataNotice } from './sample-data-notice'

/** The screens that read from the API today. */
const LIVE_SCREEN_IDS = ['SC-01', 'SC-02', 'SC-03', 'SC-04', 'SC-06', 'SC-07', 'SC-08', 'DEV-01']

/** Any screen will do. The tests set the flag themselves on a copy of it. */
function basket(): ScreenDef {
  const found = screenById('SC-04')
  if (!found) throw new Error('The inventory has no SC-04.')
  return found
}

describe('the sample data notice', () => {
  it('says so on a screen whose flag is false', () => {
    render(<SampleDataNotice screen={{ ...basket(), live: false }} />)

    expect(screen.getByRole('status')).toHaveTextContent(SAMPLE_DATA_TITLE)
    expect(screen.getByRole('status')).toHaveTextContent('nothing you change here is saved')
  })

  it('says nothing on the same screen once its flag is true', () => {
    render(<SampleDataNotice screen={{ ...basket(), live: true }} />)

    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  it('says nothing when the shell is not showing a screen at all', () => {
    render(<SampleDataNotice screen={undefined} />)

    expect(screen.getByRole('status')).toBeEmptyDOMElement()
  })

  it('announces the notice when the screen changes to one on sample data', () => {
    const live = { ...basket(), live: true }
    const { rerender } = render(<SampleDataNotice screen={live} />)
    const region = screen.getByRole('status')

    rerender(<SampleDataNotice screen={{ ...live, live: false }} />)

    // The same region is still on the page and now has words in it, which is
    // what makes a screen reader announce them.
    expect(screen.getByRole('status')).toBe(region)
    expect(region).toHaveTextContent(SAMPLE_DATA_TITLE)
  })
})

describe('the live flag in the inventory', () => {
  it('is true for the screens that read from the API and false for the rest', () => {
    const live = SCREENS.filter((candidate) => candidate.live).map((candidate) => candidate.id)

    expect(live).toEqual(LIVE_SCREEN_IDS)
  })
})
