/**
 * The question before a model is shown to customers or hidden from them, on
 * SC-20.
 *
 * Publishing says that customers can find the model and book it straight
 * away, at the figures it has now. Hiding says that it leaves the catalogue at
 * once and that bookings already made still stand. Whether the server allows
 * either is the server's to say, and a refusal shows its sentence here. The
 * list is read again once the server has answered, so the model shows where it
 * now stands.
 */

import { setModelPublication } from '../../shared/api/admin-catalogue'
import type { AdminModel } from '../../shared/api/contract'
import { WriteQuestion } from './SC20-Write-Question'
import { useCatalogueWrite } from './use-catalogue-write'

export function PublicationQuestion({
  model,
  onDone,
  onCancel,
}: {
  model: AdminModel
  /** Called once the server has answered, with whether the model is now published. */
  onDone: (published: boolean) => void
  onCancel: () => void
}) {
  const write = useCatalogueWrite('model_publication', model.id)
  const publishing = !model.isPublished

  function answer() {
    write.send(() => setModelPublication(model.id, publishing), { onAnswer: () => onDone(publishing) })
  }

  return (
    <WriteQuestion
      id={`publication-${model.id}`}
      heading={publishing ? `Publish ${model.name}?` : `Hide ${model.name} from customers?`}
      answer={publishing ? 'Yes, publish it' : 'Yes, hide it'}
      pendingAnswer={publishing ? 'Publishing it' : 'Hiding it'}
      cancel="Keep it as it is"
      refusedTitle={publishing ? 'The model was not published' : 'The model was not hidden'}
      pending={write.pending}
      failure={write.failure}
      onAnswer={answer}
      onCancel={() => {
        write.clearFailure()
        onCancel()
      }}
    >
      {publishing ? (
        <>
          <p>Customers can find it in the catalogue and book it straight away, at the figures it has now.</p>
          {model.assetCount === 0 && (
            <p>The fleet holds no unit of it yet, so customers will find it with nothing free to book.</p>
          )}
        </>
      ) : (
        <p>
          It leaves the catalogue customers browse at once, and nobody can book it until it is published again.
          Bookings already made still stand.
        </p>
      )}
    </WriteQuestion>
  )
}
