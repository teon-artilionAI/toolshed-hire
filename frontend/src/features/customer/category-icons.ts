/**
 * One icon per catalogue category, so the tiles read at a glance on a phone.
 *
 * The icons are keyed by the category code. A category carries its code, and
 * so does every model in it, so the same lookup serves a category tile and the
 * placeholder a model shows when it has no photograph. A category that arrives
 * without an entry here gets a spanner, which is better than a hole in the
 * tile.
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
  'BREAK-DRILL': Hammer,
  COMPACTION: Layers,
  'CONCRETE-MIX': Container,
  'CUT-GRIND': Disc3,
  'FLOOR-PREP': Eraser,
  'ACCESS-LIFT': MoveVertical,
  ACCESS: Fence,
  LIFTING: Forklift,
  GARDEN: Trees,
  'POWER-LIGHT': Zap,
  PUMPS: Droplets,
  WELDING: Flame,
  CLEANING: SprayCan,
  'SITE-EQUIP': Construction,
}

/**
 * The icon for a category.
 *
 * @param code The category code, as `code` on a category and `categoryCode`
 *   on a model.
 * @returns A spanner and not a hole, if a new category arrives without an icon.
 */
export function categoryIconFor(code: string): LucideIcon {
  return CATEGORY_ICON[code] ?? Wrench
}
