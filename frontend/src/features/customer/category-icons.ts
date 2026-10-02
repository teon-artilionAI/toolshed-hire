/**
 * One icon per catalogue category, so the tiles read at a glance on a phone.
 *
 * The API identifies a category by its slug, so the icons are keyed by slug
 * too. A category that arrives without an entry here gets a spanner, which is
 * better than a hole in the tile.
 */

import {
  Construction,
  Container,
  Disc3,
  Droplets,
  Eraser,
  Fence,
  Flame,
  Forklift,
  Hammer,
  Layers,
  MoveVertical,
  SprayCan,
  Trees,
  Wrench,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

const CATEGORY_ICON: Record<string, LucideIcon> = {
  'breaking-drilling': Hammer,
  compaction: Layers,
  'concrete-mixing': Container,
  'cutting-grinding': Disc3,
  'sanding-floor-preparation': Eraser,
  'access-lifting': MoveVertical,
  'ladders-trestles-towers': Fence,
  'lifting-material-handling': Forklift,
  gardening: Trees,
  'power-lighting': Zap,
  'pumps-dewatering': Droplets,
  welding: Flame,
  'cleaning-floor-care': SprayCan,
  'site-equipment': Construction,
}

/** A spanner and not a hole, if a new category arrives without an icon. */
export function categoryIconFor(slug: string): LucideIcon {
  return CATEGORY_ICON[slug] ?? Wrench
}
