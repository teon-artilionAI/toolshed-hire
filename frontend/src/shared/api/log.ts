/**
 * Structured console logging for the data layer and the session.
 *
 * Every line carries an event name and a record of context, so a failed call
 * leaves a readable trail with the method, the path and the reason and not a
 * bare message.
 *
 * Nothing that is a secret goes through here. A caller logs that a token was
 * issued or dropped and never the token itself, and never a password.
 */

export type LogLevel = 'info' | 'warn' | 'error'

/**
 * Write one event to the console.
 *
 * @param level How serious it is. A refusal is a warning, a fault is an error.
 * @param event A dotted name, for example `api.request_failed`.
 * @param context What was attempted and what came back.
 */
export function logEvent(level: LogLevel, event: string, context: Record<string, unknown>): void {
  const entry = { event, ...context }
  if (level === 'error') console.error(event, entry)
  else if (level === 'warn') console.warn(event, entry)
  else console.info(event, entry)
}
