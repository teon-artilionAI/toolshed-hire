/**
 * The hire basket, for a screen.
 *
 * The basket itself is in basket-store.ts, outside React. This subscribes a
 * component to it, so the shell's count and the basket screen redraw whenever
 * a model is added, changed or taken out, wherever that happened.
 */

import { useSyncExternalStore } from 'react'
import { basketSnapshot, subscribeToBasket } from './basket-store'
import type { Basket } from './basket-store'

export function useBasket(): Basket {
  return useSyncExternalStore(subscribeToBasket, basketSnapshot)
}
