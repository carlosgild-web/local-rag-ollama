/**
 * After a take: shown rows -> cues.json (start/end per subtitle), and the checks that make
 * the video trustworthy (decision 0043, ported from luna-hybrid-agent):
 *   - every row shown is a storyboard row; the rows that never matched are listed;
 *   - every payload on screen equals the capture it names (events.json, inspect-<turn>.json,
 *     session-<turn>.json), cut the same way (payload.mjs);
 *   - the inspector's ranking for each turn is the order the chat sent its passages;
 *   - the app answered with a model the storyboard allows, and no payload shows a local path;
 *   - a replayed take (two passes): every answer, and the passages it was given, equal pass
 *     1's run of the same question at the same point of the script.
 *
 *   node cues.mjs out/ollama            build cues.json and check
 *   node cues.mjs out/ollama --verify   check only
 */
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { isDeepStrictEqual } from 'node:util'

import { cut, hasLocalPath } from './payload.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const TAIL_MS = 1500 // the last subtitle stays this long after its hold

const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'))

export function buildCues(shown) {
  return shown.map((s, i) => ({
    id: s.id,
    start_ms: s.t_ms,
    end_ms: i + 1 < shown.length ? shown[i + 1].t_ms : s.t_ms + s.hold_ms + TAIL_MS,
    subtitle: s.subtitle,
  }))
}

/** A turn's answer, rebuilt from the capture: the streamed text and the stored message. */
function answerOf(dir, events, turn) {
  const session = readJson(join(dir, `session-${turn}.json`))
  const stored = [...session.messages].reverse().find((m) => m.role === 'assistant')
  const streamed = events.filter((e) => e.turn === turn && e.type === 'token').map((e) => e.data.text).join('')
  return { model_wrote: streamed, stored: stored.content, citation_status: stored.citation_status }
}

function verify(dir, storyboard, shown, take) {
  const problems = []
  const notes = []
  const expected = storyboard.rows.map((r) => r.id)
  const got = shown.map((s) => s.id)
  const unknown = got.filter((id) => !expected.includes(id))
  if (unknown.length) problems.push(`rows not in the storyboard: ${unknown.join(', ')}`)
  const missing = expected.filter((id) => !got.includes(id))
  if (missing.length) notes.push(`never matched (not in the video): ${missing.join(', ')}`)
  if (take.failure) problems.push(`the take failed: ${take.failure}`)

  const events = readJson(join(dir, 'events.json'))
  let checked = 0
  for (const s of shown) {
    if (!s.source) continue
    const { spec } = s.source
    let truth
    try {
      if (spec.from === 'event') truth = cut(events[s.source.index]?.data, spec)
      else if (spec.from === 'inspect') truth = cut(readJson(join(dir, `inspect-${s.source.turn}.json`)), spec)
      else if (spec.from === 'answer') truth = cut(answerOf(dir, events, s.source.turn), spec)
      else if (spec.from === 'api') truth = cut(events[s.source.index]?.data?.body, spec)
    } catch (err) {
      problems.push(`${s.id}: ${err.message}`)
      continue
    }
    checked++
    if (!isDeepStrictEqual(s.payload, truth)) problems.push(`${s.id}: the payload on screen differs from the captured ${spec.from}`)
    if (hasLocalPath(s.payload)) problems.push(`${s.id}: the payload shows a local path`)
  }

  // The inspector explains the chat's own search: the same passages, in the same order.
  const sourcesOf = (turn) => events.find((e) => e.turn === turn && e.type === 'sources')?.data ?? []
  for (const turn of take.inspected ?? []) {
    const inspect = readJson(join(dir, `inspect-${turn}.json`))
    const sent = inspect.chunks.filter((c) => c.sent).map((c) => c.chunk_id)
    const came = sourcesOf(turn).map((s) => s.chunk_id)
    if (!came.length || !isDeepStrictEqual(sent, came)) problems.push(`${turn}: the inspector ranks ${sent} but the chat sent ${came}`)
  }

  // A replayed take is pass 1, turn for turn: same passages (so the same prompt), same answer.
  if (take.replay_of) {
    const pass1Dir = resolve(HERE, '..', take.replay_of)
    const pass1 = Object.fromEntries(
      readdirSync(pass1Dir)
        .filter((f) => /^\d+-.+\.json$/.test(f))
        .map((f) => [f.replace(/^\d+-|\.json$/g, ''), readJson(join(pass1Dir, f))]),
    )
    for (const turn of take.answered ?? []) {
      const run = pass1[turn]
      if (!run) {
        problems.push(`${turn}: no pass 1 run`)
        continue
      }
      const take2 = sourcesOf(turn).map((s) => [s.chunk_id, s.filename])
      const take1 = run.sources.map((s) => [s.chunk_id, s.filename])
      const streamed = answerOf(dir, events, turn).model_wrote
      if (!isDeepStrictEqual(take2, take1)) problems.push(`${turn}: the take's passages differ from pass 1`)
      else if (streamed !== run.answer) problems.push(`${turn}: the take's answer differs from pass 1`)
      else notes.push(`${turn}: the same ${take1.length} passages and answer as pass 1 (${(run.wall_ms / 1000).toFixed(0)} s there)`)
    }
  }

  if (take.models_allowed && !take.models_allowed.includes(take.model)) problems.push(`the app answered with ${take.model}, not ${take.models_allowed.join(', ')}`)
  return { problems, checked, notes }
}

const [dirArg, flag] = process.argv.slice(2)
if (!dirArg) {
  console.error('usage: node cues.mjs out/<video> [--verify]')
  process.exit(2)
}
const dir = resolve(HERE, dirArg)
const take = existsSync(join(dir, 'take.json')) ? readJson(join(dir, 'take.json')) : {}
const storyboard = readJson(join(HERE, take.storyboard ?? 'storyboard-ollama.json'))
const shown = readJson(join(dir, 'shown.json'))
if (flag !== '--verify') {
  writeFileSync(join(dir, 'cues.json'), JSON.stringify(buildCues(shown), null, 2))
  console.log(`cues.json: ${shown.length} cues`)
}
const { problems, checked, notes } = verify(dir, storyboard, shown, take)
for (const note of notes) console.log(`note: ${note}`)
if (problems.length) {
  console.error(problems.map((p) => `FAIL ${p}`).join('\n'))
  process.exit(1)
}
console.log(`ok: ${shown.length} rows shown; ${checked} payloads equal the capture; the search rankings match; no local paths`)
