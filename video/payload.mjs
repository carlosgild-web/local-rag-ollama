/**
 * How a storyboard row's payload is cut from what the take captured (decision 0043). The
 * recorder uses it to show the payload, and cues.mjs to check it against the saved capture:
 * one function, so the two can't drift.
 *
 * A payload spec: { from, turn?, api?, pick?, limit?, fields?, head? }
 * - from: "event" (the SSE event that triggered the row), "inspect" (the retrieval
 *   inspector on the turn's own question and shelf), "answer" (the turn's streamed text and
 *   the answer as stored), or "api" (the app's last JSON answer of that kind, e.g. "intake")
 * - pick: a dotted path; limit: the first N items of an array; fields: keep only these keys
 *   of each object (or of the object itself); head: the first N lines of a text
 */

export function pick(value, path) {
  if (!path) return value
  for (const part of path.split('.')) {
    if (value == null) throw new Error(`payload path "${path}" not found`)
    value = Array.isArray(value) && part === '-1' ? value[value.length - 1] : value[/^\d+$/.test(part) ? Number(part) : part]
  }
  if (value === undefined) throw new Error(`payload path "${path}" not found`)
  return value
}

function only(value, fields) {
  if (!fields) return value
  const keep = (o) => Object.fromEntries(fields.filter((f) => o && f in o).map((f) => [f, o[f]]))
  return Array.isArray(value) ? value.map(keep) : keep(value)
}

/** The payload `spec` cut from `source` (an event's data, an inspector answer, an API answer). */
export function cut(source, spec) {
  let value = pick(source, spec.pick)
  if (spec.limit && Array.isArray(value)) value = value.slice(0, spec.limit)
  value = only(value, spec.fields)
  if (spec.head && typeof value === 'string') value = value.split('\n').slice(0, spec.head).join('\n')
  return value
}

// A Windows or home path on screen fails the take (acceptance check: no C:\MyData in frames).
// Checked on string values, not JSON text: there a newline after "directory:" reads "y:\n".
export const PATH_RE = /(?<![A-Za-z])[A-Za-z]:\\[^\s\\]|\\Users\\|\/home\/|MyData/
export const hasLocalPath = (value) =>
  typeof value === 'string'
    ? PATH_RE.test(value)
    : value !== null && typeof value === 'object'
      ? Object.values(value).some(hasLocalPath)
      : false
