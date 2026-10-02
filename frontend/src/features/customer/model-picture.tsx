/**
 * The picture of a catalogue model, on SC-01, SC-02 and SC-03.
 *
 * A model may arrive without a photograph. An empty block where the picture
 * would be reads as a page that did not finish loading, so a model with no
 * photograph gets a placeholder that is plainly meant. It is the icon of the
 * model's category on the brand wash, which is the icon and the wash the
 * category tiles on the home screen already use. A customer who came in
 * through "Compaction" sees the same mark on every compactor.
 *
 * The picture never carries the name by itself. The name of the model is real
 * text, under the banner or right beside the thumbnail, so it is read once and
 * read the same whether there is a photograph or not. The photograph and the
 * icon are both hidden from assistive technology for that reason.
 */

import { useId } from 'react'
import { categoryIconFor } from './category-icons'

/** The test id of the placeholder, so a test can tell it from a photograph. */
export const MODEL_PLACEHOLDER_TEST_ID = 'model-placeholder'

/**
 * The photograph of a model, or the placeholder when it has none.
 *
 * It fills the box it is put in, so the parent decides the size and must be
 * positioned.
 */
function ModelPicture({
  categoryCode,
  imagePath,
  iconClassName,
}: {
  /** The code of the model's category, which picks the placeholder icon. */
  categoryCode: string
  /** Same origin path to the photograph, or null when there is none. */
  imagePath: string | null
  /** The size of the placeholder icon. */
  iconClassName: string
}) {
  if (imagePath) {
    return (
      <img
        src={imagePath}
        alt=""
        loading="lazy"
        className="absolute inset-0 h-full w-full object-cover"
      />
    )
  }
  const Icon = categoryIconFor(categoryCode)
  return (
    <span
      className="absolute inset-0 flex items-center justify-center bg-accent-wash"
      data-testid={MODEL_PLACEHOLDER_TEST_ID}
      aria-hidden="true"
    >
      <span className="flex items-center justify-center rounded-full bg-surface p-md shadow-card">
        <Icon className={`${iconClassName} text-ink`} strokeWidth={1.5} />
      </span>
    </span>
  )
}

/**
 * The picture across the top of a card, with the model name under it.
 *
 * The two together are one figure, and the name is what it is called. So a
 * model with no photograph is still announced by its name, and a model with
 * one is not announced twice.
 */
export function ModelBanner({
  name,
  manufacturer,
  categoryCode,
  imagePath,
  height = 'h-24',
}: {
  name: string
  manufacturer: string
  categoryCode: string
  /** Same origin path to the photograph, or null when there is none. */
  imagePath: string | null
  /** The height of the picture, without the strip that holds the name. */
  height?: string
}) {
  const nameId = useId()
  return (
    <figure className="overflow-hidden rounded-t-lg" aria-labelledby={nameId}>
      <div className={`relative ${height}`}>
        <ModelPicture categoryCode={categoryCode} imagePath={imagePath} iconClassName="h-8 w-8" />
      </div>
      <figcaption className="bg-ink px-md py-sm">
        <p id={nameId} className="text-sm font-semibold leading-tight text-white">
          {name}
        </p>
        <p className="mt-xs font-mono text-xs text-slate-dim">{manufacturer}</p>
      </figcaption>
    </figure>
  )
}

/**
 * The small picture at the start of a search result row. The row has the name
 * of the model as its heading, so this is decoration and nothing more.
 */
export function ModelThumbnail({
  categoryCode,
  imagePath,
}: {
  categoryCode: string
  /** Same origin path to the photograph, or null when there is none. */
  imagePath: string | null
}) {
  return (
    <div className="relative h-20 shrink-0 sm:h-auto sm:w-32">
      <ModelPicture categoryCode={categoryCode} imagePath={imagePath} iconClassName="h-7 w-7" />
    </div>
  )
}
