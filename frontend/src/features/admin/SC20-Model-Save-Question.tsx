/**
 * The question before a model is added or changed on SC-20.
 *
 * Adding one says that it starts hidden from customers and that its stock code
 * cannot be changed afterwards. Changing one says what changes. Every figure
 * that moves is named with what it is now and what it will be, and when any
 * figure moves the question says, before anything is saved, that bookings
 * already made keep the rate they were booked at and only new bookings take
 * the new one. That is the server's rule as well. Every booking and hire keeps
 * its own copy of the figures.
 *
 * The figures are written as they were typed, in rand. Nothing is worked out.
 */

import type { AdminModel, ModelChangesRequest, NewModelRequest } from '../../shared/api/contract'
import { money } from '../../shared/format'
import { amountForTheWire } from '../counter/correction-model'
import type { CounterRefusal } from '../counter/counter-refusal'
import { MONEY_LABEL, moneyChangesIn } from './model-form'
import type { ModelField, MoneyField } from './model-form'
import { WriteQuestion } from './SC20-Write-Question'

/** What the details other than the figures are called in a sentence. */
const DETAIL_NOUN: Record<Exclude<ModelField, MoneyField | 'sku'>, string> = {
  name: 'the name',
  slug: 'the name in the web address',
  categoryId: 'the category',
  manufacturer: 'the manufacturer',
  modelNumber: 'the model number',
  shortDescription: 'the short description',
  longDescription: 'the full description',
  minHireDays: 'the shortest hire',
  maxHireDays: 'the longest hire',
}

/** Said whenever a figure moves, before it is saved. */
export const BOOKINGS_KEEP_THEIR_RATE =
  'Bookings already made keep the rate they were booked at. Only bookings made from now on take the new figures.'

/** An amount in rand, or what was typed when it is not an amount at all. */
function amountWords(typed: string): string {
  const amount = amountForTheWire(typed)
  return amount === null ? `"${typed}"` : money(amount)
}

/** "a", "a and b", or "a, b and c", with a capital letter at the start. */
function listWords(nouns: readonly string[]): string {
  const joined = nouns.length <= 1 ? nouns.join('') : `${nouns.slice(0, -1).join(', ')} and ${nouns.at(-1)}`
  return joined.charAt(0).toUpperCase() + joined.slice(1)
}

function changedDetails(changes: ModelChangesRequest): string[] {
  return (Object.keys(DETAIL_NOUN) as (keyof typeof DETAIL_NOUN)[])
    .filter((field) => changes[field] !== undefined)
    .map((field) => DETAIL_NOUN[field])
}

interface QuestionState {
  pending: boolean
  failure: CounterRefusal | null
  onAnswer: () => void
  onCancel: () => void
}

/** Before a new model is added. */
export function AddModelQuestion({ body, ...state }: QuestionState & { body: NewModelRequest }) {
  const name = body.name === '' ? 'this model' : body.name
  return (
    <WriteQuestion
      id="model-save"
      heading={`Add ${name} to the catalogue?`}
      answer="Yes, add it"
      pendingAnswer="Adding it"
      cancel="Go back to the form"
      refusedTitle="The model was not added"
      {...state}
    >
      <p>It goes into the catalogue hidden from customers. Publish it from the list once it is ready to be booked.</p>
      <p>Its stock code, {body.sku === '' ? 'left empty' : body.sku}, cannot be changed once it is added.</p>
    </WriteQuestion>
  )
}

/** Before a model that exists is changed. */
export function ChangeModelQuestion({
  model,
  changes,
  ...state
}: QuestionState & { model: AdminModel; changes: ModelChangesRequest }) {
  const figures = moneyChangesIn(model, changes)
  const details = changedDetails(changes)
  return (
    <WriteQuestion
      id="model-save"
      heading={`Save the changes to ${model.name}?`}
      answer="Yes, save the changes"
      pendingAnswer="Saving the changes"
      cancel="Go back to the form"
      refusedTitle="The changes were not saved"
      {...state}
    >
      {figures.length > 0 && (
        <ul className="list-disc pl-lg">
          {figures.map((figure) => (
            <li key={figure.field}>
              The {MONEY_LABEL[figure.field].toLowerCase()} goes from {money(figure.before)} to{' '}
              {amountWords(figure.after)}.
            </li>
          ))}
        </ul>
      )}
      {details.length > 0 && (
        <p>
          {listWords(details)} {details.length === 1 ? 'changes' : 'change'}
          {figures.length > 0 ? ' as well' : ''}.
        </p>
      )}
      {figures.length > 0 && <p className="font-semibold">{BOOKINGS_KEEP_THEIR_RATE}</p>}
    </WriteQuestion>
  )
}
