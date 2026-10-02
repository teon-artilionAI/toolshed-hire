/**
 * Tests for the picture of a model and the placeholder that stands in for it.
 *
 * Every seeded model has no photograph, so the placeholder is what a customer
 * actually sees. I check that it is there, that it carries the icon of the
 * model's category, and that the model is still called by its name.
 */

import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MODEL_PLACEHOLDER_TEST_ID, ModelBanner, ModelThumbnail } from './model-picture'

const PHOTOGRAPH = '/images/models/cp-100.jpg'

/** The class the icon set puts on one of its icons, for example `lucide-layers`. */
function iconClass(placeholder: HTMLElement): string {
  const icon = placeholder.querySelector('svg')
  if (!icon) throw new Error('The placeholder holds no icon.')
  return icon.getAttribute('class') ?? ''
}

function banner(categoryCode: string, imagePath: string | null) {
  return render(
    <ModelBanner
      name="CP 100 Plate Compactor"
      manufacturer="Wacker Neuson"
      categoryCode={categoryCode}
      imagePath={imagePath}
    />,
  )
}

describe('ModelBanner', () => {
  it('shows a placeholder with the icon of the category when there is no photograph', () => {
    banner('COMPACTION', null)

    const placeholder = screen.getByTestId(MODEL_PLACEHOLDER_TEST_ID)
    expect(iconClass(placeholder)).toContain('lucide-layers')
    expect(document.querySelector('img')).not.toBeInTheDocument()
  })

  it('is called by the name of the model, and shows the name and the maker as text', () => {
    banner('COMPACTION', null)

    const picture = screen.getByRole('figure', { name: 'CP 100 Plate Compactor' })
    expect(within(picture).getByText('CP 100 Plate Compactor')).toBeVisible()
    expect(within(picture).getByText('Wacker Neuson')).toBeVisible()
  })

  it('keeps the icon away from assistive technology, so the name is read once', () => {
    banner('COMPACTION', null)

    expect(screen.getByTestId(MODEL_PLACEHOLDER_TEST_ID)).toHaveAttribute('aria-hidden', 'true')
  })

  it('gives each category its own icon', () => {
    const { unmount } = banner('COMPACTION', null)
    const compaction = iconClass(screen.getByTestId(MODEL_PLACEHOLDER_TEST_ID))
    unmount()
    banner('WELDING', null)

    expect(iconClass(screen.getByTestId(MODEL_PLACEHOLDER_TEST_ID))).not.toBe(compaction)
  })

  it('falls back to a spanner for a category it has no icon for', () => {
    banner('SOMETHING-NEW', null)

    expect(iconClass(screen.getByTestId(MODEL_PLACEHOLDER_TEST_ID))).toContain('lucide-wrench')
  })

  it('shows the photograph and no placeholder when the model has one', () => {
    banner('COMPACTION', PHOTOGRAPH)

    expect(screen.queryByTestId(MODEL_PLACEHOLDER_TEST_ID)).not.toBeInTheDocument()
    const photograph = document.querySelector('img')
    expect(photograph).toHaveAttribute('src', PHOTOGRAPH)
    // The name under it says what it is, so the photograph itself is decoration.
    expect(photograph).toHaveAttribute('alt', '')
    expect(screen.getByRole('figure', { name: 'CP 100 Plate Compactor' })).toBeVisible()
  })
})

describe('ModelThumbnail', () => {
  it('shows the placeholder with the icon of the category when there is no photograph', () => {
    render(<ModelThumbnail categoryCode="GARDEN" imagePath={null} />)

    const placeholder = screen.getByTestId(MODEL_PLACEHOLDER_TEST_ID)
    expect(iconClass(placeholder)).toContain('lucide-trees')
    expect(placeholder).toHaveAttribute('aria-hidden', 'true')
  })

  it('shows the photograph when the model has one', () => {
    render(<ModelThumbnail categoryCode="GARDEN" imagePath={PHOTOGRAPH} />)

    expect(screen.queryByTestId(MODEL_PLACEHOLDER_TEST_ID)).not.toBeInTheDocument()
    expect(document.querySelector('img')).toHaveAttribute('src', PHOTOGRAPH)
  })
})
