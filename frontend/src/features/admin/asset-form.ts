/**
 * The two forms of SC-21, registering a unit and changing its paperwork, and
 * the bodies they are sent as.
 *
 * Every field carries the name the API gives it, so a message the API sends
 * about a field lands under that field with no table in between.
 *
 * The browser holds no copy of the rules about tags, money, dates or meter
 * readings. A tag in the wrong form or carried by another unit, a cost below
 * zero, a day after today and a reading below zero are all the server's to
 * refuse, and its 422 puts each sentence under its field. The forms only check
 * what they need to write a body at all. A model and a branch have to be
 * chosen, the day it was bought has to be given, and a meter reading has to be
 * a whole number or left empty.
 *
 * The cost is sent the way the API takes money, with two decimals, written out
 * by its digits and never through a float. One that is not an amount at all
 * is sent as it was typed, so the server says what is wrong with it, and the
 * form says that in plain words, the way SC-20 does for a figure.
 */

import type {
  AdminAsset,
  AssetChangesRequest,
  ConditionGrade,
  NewAssetRequest,
} from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { CONDITION_GRADES } from '../../shared/api/rental-read'
import { moneyForTheWire, plainAmountWords } from './model-form'

/** What the owner is typing to register a unit, one string for each field. */
export interface NewAssetDraft {
  assetTag: string
  modelId: string
  branchCode: string
  serialNumber: string
  conditionGrade: string
  acquiredOn: string
  acquisitionCost: string
  hourMeterReading: string
  notes: string
}

export type NewAssetField = keyof NewAssetDraft

/** What the owner is typing to change a unit's paperwork. */
export type AssetChangesDraft = Pick<NewAssetDraft, 'serialNumber' | 'conditionGrade' | 'hourMeterReading' | 'notes'>

export type AssetChangesField = keyof AssetChangesDraft

export type AssetDraftErrors = Partial<Record<NewAssetField, string>>

/** Reading order of the registration form, which is also the order problems are listed in. */
export const NEW_ASSET_FIELD_ORDER: readonly NewAssetField[] = [
  'assetTag',
  'modelId',
  'branchCode',
  'serialNumber',
  'conditionGrade',
  'acquiredOn',
  'acquisitionCost',
  'hourMeterReading',
  'notes',
]

/** Reading order of the form that changes a unit's paperwork. */
export const ASSET_CHANGES_FIELD_ORDER: readonly AssetChangesField[] = [
  'serialNumber',
  'conditionGrade',
  'hourMeterReading',
  'notes',
]

/** The grade a new unit is offered at first. It is in the building and unused. */
const FIRST_GRADE: ConditionGrade = 'A'

const WHOLE_NUMBER = /^-?\d+$/

const CHOOSE_A_MODEL = 'Choose the model this unit is.'
const CHOOSE_A_BRANCH = 'Choose the branch the unit belongs to.'
const GIVE_THE_DAY = 'Enter the day the unit was bought.'
const CHOOSE_A_GRADE = 'Choose the grade the unit is in.'
const WHOLE_HOURS = 'Enter the hours on the meter as a whole number, or leave it empty if the unit has no meter.'

/** A new unit, with nothing filled in but the grade. */
export const EMPTY_NEW_ASSET_DRAFT: NewAssetDraft = {
  assetTag: '',
  modelId: '',
  branchCode: '',
  serialNumber: '',
  conditionGrade: FIRST_GRADE,
  acquiredOn: '',
  acquisitionCost: '',
  hourMeterReading: '',
  notes: '',
}

/** The id of the control for a field, which a problem above the form links to. */
export function assetFieldId(field: NewAssetField): string {
  return `asset-${field}`
}

function optionalText(typed: string): string | null {
  const trimmed = typed.trim()
  return trimmed === '' ? null : trimmed
}

/** A meter reading as a number, null for none, or undefined when it is not a whole number. */
function readingOf(typed: string): number | null | undefined {
  const trimmed = typed.trim()
  if (trimmed === '') return null
  return WHOLE_NUMBER.test(trimmed) ? Number(trimmed) : undefined
}

function gradeOf(typed: string): ConditionGrade | undefined {
  return CONDITION_GRADES.find((grade) => grade === typed)
}

/** Either the body to send, or why the form cannot be written as one yet. */
export type Checked<Body> = { body: Body; errors: null } | { body: null; errors: AssetDraftErrors }

/** The body of a new unit, with every field the route takes. */
export function newAssetRequestFrom(draft: NewAssetDraft): Checked<NewAssetRequest> {
  const errors: AssetDraftErrors = {}
  if (draft.modelId === '') errors.modelId = CHOOSE_A_MODEL
  if (draft.branchCode === '') errors.branchCode = CHOOSE_A_BRANCH
  if (draft.acquiredOn.trim() === '') errors.acquiredOn = GIVE_THE_DAY
  const grade = gradeOf(draft.conditionGrade)
  if (grade === undefined) errors.conditionGrade = CHOOSE_A_GRADE
  const reading = readingOf(draft.hourMeterReading)
  if (reading === undefined) errors.hourMeterReading = WHOLE_HOURS
  if (Object.keys(errors).length > 0 || grade === undefined || reading === undefined) return { body: null, errors }
  return {
    errors: null,
    body: {
      assetTag: draft.assetTag.trim(),
      modelId: draft.modelId,
      branchCode: draft.branchCode,
      serialNumber: optionalText(draft.serialNumber),
      conditionGrade: grade,
      acquiredOn: draft.acquiredOn.trim(),
      acquisitionCost: moneyForTheWire(draft.acquisitionCost),
      hourMeterReading: reading,
      notes: optionalText(draft.notes),
    },
  }
}

/** The form for a unit that exists, holding what the server holds. */
export function draftOfAsset(unit: AdminAsset): AssetChangesDraft {
  return {
    serialNumber: unit.serialNumber ?? '',
    conditionGrade: unit.conditionGrade,
    hourMeterReading: unit.hourMeterReading === null ? '' : String(unit.hourMeterReading),
    notes: unit.notes ?? '',
  }
}

/**
 * The body of a change, with only the fields that differ from what the server
 * holds. The tag, the model and the branch are never among them, because they
 * never change. An empty body means nothing was changed.
 */
export function assetChangesFrom(unit: AdminAsset, draft: AssetChangesDraft): Checked<AssetChangesRequest> {
  const grade = gradeOf(draft.conditionGrade)
  const reading = readingOf(draft.hourMeterReading)
  const errors: AssetDraftErrors = {}
  if (grade === undefined) errors.conditionGrade = CHOOSE_A_GRADE
  if (reading === undefined) errors.hourMeterReading = WHOLE_HOURS
  if (grade === undefined || reading === undefined) return { body: null, errors }
  const changes: AssetChangesRequest = {}
  const serialNumber = optionalText(draft.serialNumber)
  if (serialNumber !== unit.serialNumber) changes.serialNumber = serialNumber
  if (grade !== unit.conditionGrade) changes.conditionGrade = grade
  if (reading !== unit.hourMeterReading) changes.hourMeterReading = reading
  const notes = optionalText(draft.notes)
  if (notes !== unit.notes) changes.notes = notes
  return { body: changes, errors: null }
}

/**
 * The server's messages for a refused registration, with one about a cost it
 * could not read as an amount put in plain words. Whether it could is told
 * from what was sent, never from the words of its message.
 */
export function plainCostMessage(fields: FieldErrors, sent: NewAssetRequest): FieldErrors {
  if (fields.acquisitionCost === undefined) return fields
  const words = plainAmountWords(sent.acquisitionCost)
  return words === null ? fields : { ...fields, acquisitionCost: words }
}
