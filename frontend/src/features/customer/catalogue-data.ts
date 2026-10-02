/**
 * Fixture catalogue lookups for the hire basket, SC-04.
 *
 * SC-01 to SC-03 read the catalogue from the API and no longer come here. The
 * basket has not moved over yet, so it still asks the fixtures two questions.
 * What do we hire, and which model is this. This module goes when the basket
 * does.
 */

import { productModels } from '../../shared/fixtures'
import type { ProductModel, Uuid } from '../../shared/types'

/** Only published models are ever shown to a customer. */
export const catalogue: ProductModel[] = productModels.filter((m) => m.published)

/** Looks through every model, published or not, so an unpublished one can
 *  be told apart from an address that means nothing. */
export function modelById(id: Uuid): ProductModel | undefined {
  return productModels.find((m) => m.id === id)
}

/**
 * The slug the API knows a fixture model by.
 *
 * The model detail screen is addressed by slug now, and the fixtures carry no
 * slug. The seeded catalogue builds each slug from the model name, lower case
 * with a hyphen for every run of other characters, so the same rule here gives
 * the same slug for every model the fixtures hold.
 */
export function modelSlug(model: ProductModel): string {
  return model.name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** The fixture model behind a slug, for a link that arrives from SC-03. */
export function modelBySlug(slug: string): ProductModel | undefined {
  return productModels.find((m) => modelSlug(m) === slug)
}
