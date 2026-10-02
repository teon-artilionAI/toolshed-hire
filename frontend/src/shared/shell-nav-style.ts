/**
 * The class names the navigation shares, and the limit of the phone tab bar.
 *
 * They sit apart from the components that use them so both the shell and its
 * navigation can import them.
 */

/** Most items a phone tab bar can carry before labels stop being legible. */
export const MAX_TAB_BAR_ITEMS = 5

/** One tab. 56px tall with 8px between neighbours, which is what a thumb
 *  at a counter needs. */
export const TAB_CLASS =
  'flex min-h-[3.5rem] flex-1 cursor-pointer flex-col items-center justify-center gap-xs rounded px-xs py-sm text-xs leading-tight transition-colors'

/** Active state is amber with ink text, which passes contrast where amber
 *  with white would not. */
export function navItemClass(
  base: string,
  idle: string,
  active = 'bg-accent font-semibold text-accent-ink',
) {
  return ({ isActive }: { isActive: boolean }) =>
    `${base} ${isActive ? active : idle}`
}
