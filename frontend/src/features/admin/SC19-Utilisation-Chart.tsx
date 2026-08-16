/**
 * The one chart on SC-19, drawn as inline SVG rather than by pulling in a
 * charting library for a single figure.
 *
 * It is a magnitude comparison of one measure across three branches, so it
 * is a plain bar chart with one bar per branch. There is a single series,
 * which means no legend is needed and no hue carries meaning: the
 * percentage is printed beside every bar and repeated in the branch table
 * below, so the chart survives greyscale printing and colour blindness.
 */

import type { BranchPosition } from './admin-fleet'
import { UTILISATION_TARGET } from './admin-fleet'

const ROW_HEIGHT = 40
const TOP_GUTTER = 18
const TRACK_X = 46
const TRACK_WIDTH = 300
const VIEW_WIDTH = 400
const BAR_HEIGHT = 12

export default function UtilisationChart({ rows }: { rows: BranchPosition[] }) {
  const height = TOP_GUTTER + rows.length * ROW_HEIGHT
  const targetX = TRACK_X + (TRACK_WIDTH * UTILISATION_TARGET) / 100
  const spoken = rows
    .map((r) => `${r.name}, ${r.utilisation} percent, ${r.onHire} of ${r.units} units on hire`)
    .join('. ')

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Fleet utilisation by branch, against a target of ${UTILISATION_TARGET} percent. ${spoken}.`}
      >
        <title>Fleet utilisation by branch</title>
        <line
          x1={targetX}
          y1={12}
          x2={targetX}
          y2={height - 6}
          className="stroke-slate-faint"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
        <text x={targetX} y={8} textAnchor="middle" fontSize={9} className="fill-slate-soft">
          Target {UTILISATION_TARGET}%
        </text>
        {rows.map((row, index) => {
          const y = TOP_GUTTER + index * ROW_HEIGHT
          const barWidth = Math.max(2, (TRACK_WIDTH * row.utilisation) / 100)
          return (
            <g key={row.code}>
              <text x={0} y={y + 18} fontSize={12} className="fill-ink font-medium">
                {row.code}
              </text>
              <rect
                x={TRACK_X} y={y + 6} width={TRACK_WIDTH} height={BAR_HEIGHT}
                rx={4} className="fill-muted"
              />
              <rect
                x={TRACK_X} y={y + 6} width={barWidth} height={BAR_HEIGHT}
                rx={4} className="fill-slate"
              />
              <text
                x={VIEW_WIDTH} y={y + 18} textAnchor="end" fontSize={12}
                className="fill-ink font-semibold"
              >
                {row.utilisation}%
              </text>
              <text x={TRACK_X} y={y + 32} fontSize={9} className="fill-slate-soft">
                {row.onHire} of {row.units} units on hire, {row.offRoad} off the road
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption className="mt-sm text-xs text-slate-soft">
        CBD is Cape Town CBD, BEL is Bellville and SOM is Somerset West. Retired
        and lost units are left out of the utilisation figure because they are no
        longer part of the fleet.
      </figcaption>
    </figure>
  )
}
