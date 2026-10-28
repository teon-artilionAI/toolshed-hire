/**
 * The photographs of the damage on one of the customer's own hires, on SC-09
 * (#112).
 *
 * Only a hire whose damage was reported offers them, which is a hire with a
 * unit whose damage assessment is done. The list is not read when the page
 * opens. A "Damage photographs" button opens it and reads it then, so a page
 * of hires costs no more requests than it did, however many of them had
 * damage. Each photograph is a tile that opens it as a download, through a
 * link the API makes for this customer and this hire alone.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ImageDown } from 'lucide-react'
import type { Rental } from '../../shared/api/contract'
import { damagePhotoQueries } from '../../shared/api/damage-photo-queries'
import { myHirePhotoLink } from '../../shared/api/damage-photos'
import { DamagePhotoList } from '../../shared/damage-photo-list'

/** Whether a damage report was filed on any unit of the hire. */
function hadDamage(rental: Rental): boolean {
  return rental.items.some((item) => item.damageAssessment === 'DONE')
}

/** The damage photographs of a hire, or nothing for a hire with no damage reported. */
export function HireDamagePhotos({ rental }: { rental: Rental }) {
  const [open, setOpen] = useState(false)
  const damaged = hadDamage(rental)
  const photos = useQuery({ ...damagePhotoQueries.ofMyHire(rental.id), enabled: open && damaged })
  const panelId = `hire-photos-${rental.id}`
  if (!damaged) return null
  return (
    <div className="mt-md min-w-0">
      <button
        type="button"
        className="btn-secondary px-md"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((shown) => !shown)}
      >
        <ImageDown className="h-4 w-4 shrink-0" aria-hidden="true" />
        Damage photographs{' '}
        <span className="sr-only">of {rental.reference}</span>
        <ChevronDown
          className={`h-4 w-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        />
      </button>
      <div id={panelId} hidden={!open} className="mt-sm">
        {open && (
          <DamagePhotoList
            photos={photos}
            what={`the damage photographs of ${rental.reference}`}
            empty="No photographs were taken of the damage on this hire."
            label={`Damage photographs of ${rental.reference}`}
            openLink={(photo) => myHirePhotoLink(rental.id, photo.id)}
          />
        )}
      </div>
    </div>
  )
}
