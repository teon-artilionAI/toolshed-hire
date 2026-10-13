/**
 * The photographs of one damage report on SC-16 (#83, #112).
 *
 * Every report on the unit's record lists its photographs, oldest first, as
 * tiles that each open one as a download. The counter sees them beside the
 * report, and so does the owner while resolving it and recording the cost.
 *
 * An open report also offers the control that adds one, to the counter and to
 * the owner, until it holds six. The server refuses an assistant at another
 * branch, and the control shows that refusal as it shows any other. A closed
 * report keeps its photographs and takes no more.
 *
 * While photographs are switched off in this deployment, the server's
 * sentence stands in place of the list and the control.
 */

import { useQuery } from '@tanstack/react-query'
import type { DamageReport } from '../../shared/api/contract'
import { damagePhotoQueries, photoListState } from '../../shared/api/damage-photo-queries'
import { MAX_PHOTOS_PER_REPORT, reportPhotoLink } from '../../shared/api/damage-photos'
import { DamagePhotoList } from '../../shared/damage-photo-list'
import { REPORT_FULL } from './photo-checks'
import { PhotoUpload } from './SC16-Photo-Upload'

export function ReportPhotos({ report, canAdd }: { report: DamageReport; canAdd: boolean }) {
  const photos = useQuery(damagePhotoQueries.ofReport(report.id))
  const { switchedOff, count } = photoListState(photos)
  const headingId = `damage-photos-${report.id}`
  return (
    <section aria-labelledby={headingId} className="mt-md min-w-0 border-t border-line pt-md">
      <h4 id={headingId} className="mb-sm text-xs font-semibold uppercase tracking-wide text-slate-soft">
        Photographs{' '}
        <span className="sr-only">of {report.reference}</span>
      </h4>
      <DamagePhotoList
        photos={photos}
        what={`the photographs of ${report.reference}`}
        empty="No photographs of this damage yet."
        label={`Photographs of ${report.reference}`}
        openLink={(photo) => reportPhotoLink(report.id, photo.id)}
      />
      {canAdd && !switchedOff && count !== null && count >= MAX_PHOTOS_PER_REPORT && (
        <p className="mt-sm text-sm text-slate-soft">{REPORT_FULL}</p>
      )}
      {canAdd && !switchedOff && count !== null && count < MAX_PHOTOS_PER_REPORT && (
        <PhotoUpload reportId={report.id} reference={report.reference} remaining={MAX_PHOTOS_PER_REPORT - count} />
      )}
    </section>
  )
}
