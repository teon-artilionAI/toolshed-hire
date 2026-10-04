/**
 * The model form of SC-20, and the bodies it is sent as.
 *
 * Every field carries the name the API gives it, so a message the API sends
 * about a field lands under that field with no table in between.
 *
 * The browser holds no copy of the rules about money, codes or hire lengths.
 * A rate below zero, a weekly rate above seven days at the daily rate, a stock
 * code already in use or a shortest hire longer than the longest are all the
 * server's to refuse, and its 422 puts each sentence under its field. The
 * form only checks what it needs to write a body at all. A category has to be
 * chosen, and a number of days has to be a whole number.
 *
 * An amount is sent the way the API takes money, with two decimals, written
 * out by its digits and never through a float. One that is not an amount at
 * all is sent as it was typed, so the server says what is wrong with it. The
 * server says that in its framework's words, which quote a pattern, so the
 * form puts it in plain words under the same field.
 */

import type { AdminModel, Money, ModelChangesRequest, NewModelRequest } from '../../shared/api/contract'
import type { FieldErrors } from '../../shared/api/problem-fields'
import { amountForTheWire } from '../counter/correction-model'

/** What the owner is typing, one string for each field. */
export interface ModelDraft {
  sku: string
  name: string
  slug: string
  categoryId: string
  manufacturer: string
  modelNumber: string
  shortDescription: string
  longDescription: string
  dailyRate: string
  weeklyRate: string
  depositAmount: string
  lateFeePerDay: string
  replacementValue: string
  minHireDays: string
  maxHireDays: string
}

export type ModelField = keyof ModelDraft
export type ModelDraftErrors = Partial<Record<ModelField, string>>

/** Reading order of the form, which is also the order problems are listed in. */
export const MODEL_FIELD_ORDER: readonly ModelField[] = [
  'sku',
  'name',
  'slug',
  'categoryId',
  'manufacturer',
  'modelNumber',
  'shortDescription',
  'longDescription',
  'dailyRate',
  'weeklyRate',
  'depositAmount',
  'lateFeePerDay',
  'replacementValue',
  'minHireDays',
  'maxHireDays',
]

/** The five figures of a model that are money. */
export const MONEY_FIELDS = ['dailyRate', 'weeklyRate', 'depositAmount', 'lateFeePerDay', 'replacementValue'] as const
export type MoneyField = (typeof MONEY_FIELDS)[number]

/** What each figure is called on the screen. */
export const MONEY_LABEL: Record<MoneyField, string> = {
  dailyRate: 'Daily rate',
  weeklyRate: 'Weekly rate',
  depositAmount: 'Deposit',
  lateFeePerDay: 'Late fee per day',
  replacementValue: 'Replacement value',
}

/** The two whole numbers of a model. */
const DAY_FIELDS = ['minHireDays', 'maxHireDays'] as const

/** The text fields of a model that are sent as typed, trimmed. */
const TEXT_FIELDS = ['name', 'slug', 'manufacturer', 'modelNumber', 'shortDescription'] as const

const WHOLE_NUMBER = /^\d+$/

/** Money in the form the API reads it in a request, up to ten digits of rand
 *  and two of cents. It refuses any other form before a rule of its own runs. */
const MONEY_THE_API_READS = /^-?\d{1,10}(\.\d{1,2})?$/

const CHOOSE_A_CATEGORY = 'Choose the category the model sits in.'
const WHOLE_DAYS = 'Enter a whole number of days, for example 1.'
const NOT_AN_AMOUNT = 'Enter an amount in rand, for example 280.00.'
const TOO_LARGE_AN_AMOUNT = 'Enter an amount of at most R9,999,999,999.99.'

/** A new model, with nothing filled in. */
export const EMPTY_MODEL_DRAFT: ModelDraft = {
  sku: '',
  name: '',
  slug: '',
  categoryId: '',
  manufacturer: '',
  modelNumber: '',
  shortDescription: '',
  longDescription: '',
  dailyRate: '',
  weeklyRate: '',
  depositAmount: '',
  lateFeePerDay: '',
  replacementValue: '',
  minHireDays: '',
  maxHireDays: '',
}

/** The form for a model that exists, holding what the server holds. */
export function draftOfModel(model: AdminModel): ModelDraft {
  return {
    sku: model.sku,
    name: model.name,
    slug: model.slug,
    categoryId: model.categoryId,
    manufacturer: model.manufacturer,
    modelNumber: model.modelNumber,
    shortDescription: model.shortDescription,
    longDescription: model.longDescription ?? '',
    dailyRate: model.dailyRate,
    weeklyRate: model.weeklyRate,
    depositAmount: model.depositAmount,
    lateFeePerDay: model.lateFeePerDay,
    replacementValue: model.replacementValue,
    minHireDays: String(model.minHireDays),
    maxHireDays: String(model.maxHireDays),
  }
}

/**
 * An amount as the API takes money. Two decimals when it was typed as rand and
 * cents, such as "51" or "51,5". Anything else goes as it was typed, so the
 * server can say what is wrong with it.
 */
export function moneyForTheWire(typed: string): string {
  return amountForTheWire(typed) ?? typed.trim()
}

function wholeNumberOf(typed: string): number | null {
  const trimmed = typed.trim()
  return WHOLE_NUMBER.test(trimmed) ? Number(trimmed) : null
}

function optionalText(typed: string): string | null {
  const trimmed = typed.trim()
  return trimmed === '' ? null : trimmed
}

/** Either the body to send, or why the form cannot be written as one yet. */
export type Checked<Body> = { body: Body; errors: null } | { body: null; errors: ModelDraftErrors }

function draftProblems(draft: ModelDraft): ModelDraftErrors {
  const errors: ModelDraftErrors = {}
  if (draft.categoryId === '') errors.categoryId = CHOOSE_A_CATEGORY
  for (const field of DAY_FIELDS) if (wholeNumberOf(draft[field]) === null) errors[field] = WHOLE_DAYS
  return errors
}

/** The body of a new model, with every field the route takes. */
export function newModelRequestFrom(draft: ModelDraft): Checked<NewModelRequest> {
  const errors = draftProblems(draft)
  const minHireDays = wholeNumberOf(draft.minHireDays)
  const maxHireDays = wholeNumberOf(draft.maxHireDays)
  if (Object.keys(errors).length > 0 || minHireDays === null || maxHireDays === null) return { body: null, errors }
  return {
    errors: null,
    body: {
      sku: draft.sku.trim(),
      name: draft.name.trim(),
      slug: draft.slug.trim(),
      categoryId: draft.categoryId,
      manufacturer: draft.manufacturer.trim(),
      modelNumber: draft.modelNumber.trim(),
      shortDescription: draft.shortDescription.trim(),
      longDescription: optionalText(draft.longDescription),
      dailyRate: moneyForTheWire(draft.dailyRate),
      weeklyRate: moneyForTheWire(draft.weeklyRate),
      depositAmount: moneyForTheWire(draft.depositAmount),
      lateFeePerDay: moneyForTheWire(draft.lateFeePerDay),
      replacementValue: moneyForTheWire(draft.replacementValue),
      minHireDays,
      maxHireDays,
    },
  }
}

/**
 * The body of a change, with only the fields that differ from what the server
 * holds. The stock code is never among them, because it never changes. An
 * empty body means nothing was changed.
 */
export function modelChangesFrom(model: AdminModel, draft: ModelDraft): Checked<ModelChangesRequest> {
  const errors = draftProblems(draft)
  if (Object.keys(errors).length > 0) return { body: null, errors }
  const changes: ModelChangesRequest = {}
  for (const field of TEXT_FIELDS) {
    const typed = draft[field].trim()
    if (typed !== model[field]) changes[field] = typed
  }
  if (draft.categoryId !== model.categoryId) changes.categoryId = draft.categoryId
  const longDescription = optionalText(draft.longDescription)
  if (longDescription !== model.longDescription) changes.longDescription = longDescription
  for (const field of MONEY_FIELDS) {
    const typed = moneyForTheWire(draft[field])
    if (typed !== model[field]) changes[field] = typed
  }
  for (const field of DAY_FIELDS) {
    const typed = wholeNumberOf(draft[field])
    if (typed !== null && typed !== model[field]) changes[field] = typed
  }
  return { body: changes, errors: null }
}

/** One figure a change moves, as it is now and as it will be. */
export interface MoneyChange {
  field: MoneyField
  before: Money
  after: string
}

/**
 * The server's messages for a refused body, with each one about a figure it
 * could not read as an amount put in plain words.
 *
 * Whether the server could read a figure is told from what was sent, never
 * from the words of its message. A figure the browser could not read either is
 * not an amount at all, and one it could is too large. Each message stays
 * under its own field, so the list above the form still links to the box.
 *
 * @param fields The messages the server sent, by field.
 * @param sent The body that was refused.
 */
export function plainMoneyMessages(fields: FieldErrors, sent: NewModelRequest | ModelChangesRequest): FieldErrors {
  const plain: Record<string, string> = { ...fields }
  for (const field of MONEY_FIELDS) {
    const value = sent[field]
    if (plain[field] === undefined || value === undefined || MONEY_THE_API_READS.test(value)) continue
    plain[field] = amountForTheWire(value) === null ? NOT_AN_AMOUNT : TOO_LARGE_AN_AMOUNT
  }
  return plain
}

/** Whether a change moves any figure. */
export function movesAFigure(changes: ModelChangesRequest): boolean {
  return MONEY_FIELDS.some((field) => changes[field] !== undefined)
}

/** The id of the control for a field, which a problem above the form links to. */
export function modelFieldId(field: ModelField): string {
  return `model-${field}`
}

/** The money figures a change moves, in the order the form shows them. */
export function moneyChangesIn(model: AdminModel, changes: ModelChangesRequest): MoneyChange[] {
  return MONEY_FIELDS.flatMap((field) => {
    const after = changes[field]
    return after === undefined ? [] : [{ field, before: model[field], after }]
  })
}
