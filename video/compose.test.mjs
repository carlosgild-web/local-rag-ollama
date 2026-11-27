/** `node --test` (npm run video:test): how compose.mjs cuts a take (decision 0043). */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { findGaps, mapper, planPieces, srt, takeWaits, zoomRect } from './compose.mjs'

test('a take without a desktop clip is one piece', () => {
  assert.deepEqual(planPieces(50, []), [{ src: 'take', from: 0, to: 50 }])
})

test('model waits are shortened to 1 s and say how long they really were', () => {
  const pieces = planPieces(140, [{ from: 10, to: 68, what: 'waiting for the model' }])
  assert.deepEqual(pieces, [
    { src: 'take', from: 0, to: 10 },
    { src: 'take', from: 10, to: 11, label: 'waiting for the model: 58 s, shortened to 1 s' },
    { src: 'take', from: 68, to: 140 },
  ])
})

test('waits the take wrote are cut the same way; a short one is kept as it is', () => {
  assert.deepEqual(takeWaits([{ from_ms: 30_000, to_ms: 52_000, what: 'the inspector loading' }]), [
    { from: 30, to: 52, what: 'the inspector loading' },
  ])
  assert.deepEqual(takeWaits([{ from_ms: 0, to_ms: 2_500, what: 'x' }]), [])
})

test('model waits are found only inside a chat turn, between events', () => {
  const events = [
    { type: 'request', t_ms: 0 },
    { type: 'llm', t_ms: 41_000 },
    { type: 'tool', t_ms: 41_200 },
    { type: 'done', t_ms: 70_000 },
    { type: 'inspect', t_ms: 90_000 },
  ]
  assert.deepEqual(findGaps(events, []), [
    { from: 0.8, to: 41, what: 'waiting for the model' },
    { from: 42, to: 70, what: 'waiting for the model' },
  ])
})

test('a row on screen is never cut: the wait ends where the row starts', () => {
  const events = [{ type: 'request', t_ms: 0 }, { type: 'done', t_ms: 30_000 }]
  const shown = [{ t_ms: 10_000, hold_ms: 5_000 }]
  assert.deepEqual(findGaps(events, shown), [
    { from: 0.8, to: 10, what: 'waiting for the model' },
    { from: 15, to: 30, what: 'waiting for the model' },
  ])
})

test('a desktop clip replaces the take where it was recorded; an overlapping wait is dropped', () => {
  const clip = { clip: 'desktop', start_ms: 100_000, end_ms: 116_000 }
  const pieces = planPieces(140, takeWaits([{ from_ms: 110_000, to_ms: 125_000, what: 'x' }]), [clip])
  assert.deepEqual(pieces.map((p) => p.src), ['take', 'clip', 'take'])
})

test('times map onto the cut video; a time inside a shortened wait stays inside it', () => {
  const pieces = planPieces(60, [{ from: 10, to: 20 }])
  const map = mapper(pieces, [10, 1, 40])
  assert.equal(map(5_000), 5_000)
  assert.equal(map(15_000), 11_000)
  assert.equal(map(25_000), 16_000)
})

test('the zoom crop stays inside the capture, in the stage aspect ratio', () => {
  const crop = zoomRect({ width: 1920, height: 982 }, { factor: 2.5, cx: 0.5, cy: 0.9 })
  assert.ok(crop.x >= 0 && crop.x + crop.w <= 1920)
  assert.ok(crop.y >= 0 && crop.y + crop.h <= 982)
  assert.ok(Math.abs(crop.w / crop.h - 2) < 0.02)
})

test('srt numbers the cues and formats the times', () => {
  assert.equal(srt([{ start_ms: 1500, end_ms: 62_000, subtitle: 'Hi' }]), '1\n00:00:01,500 --> 00:01:02,000\nHi\n')
})
