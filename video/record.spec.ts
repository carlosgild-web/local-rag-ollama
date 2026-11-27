/**
 * The README video take (decision 0043, ported from luna-hybrid-agent). Drives the running app
 * inside the 1920x1080 stage and shows each storyboard row when its captured event arrives.
 *
 *   npm run video:smoke      ~10 s: the stage layout at 1920x1080 (any running app)
 *   npm run video:dry        the whole take on scripted answers (replay_server.py --dry)
 *   npm run video:ollama     the take on pass 1's qwen2.5:3b answers (replay_server.py)
 *
 * Capture: an init script wraps the app's fetch. Every SSE event of POST /api/chat goes to
 * Node with its time, and is handed to the app only when Node returns: that is how a
 * subtitle stays on screen while the app shows that step. The app and the events are not
 * changed; only their delivery to the browser is paced. The app's own JSON answers that
 * rows show (the intake's suggestions, the inspector, the evaluation comparison, a
 * rollback) are copied as they arrive. When a turn's passages arrive, the take asks the
 * retrieval inspector (POST /api/retrieve/inspect, read only) how that search ranked them;
 * after the turn, it reads the stored answer (GET /api/sessions/{id}).
 */
import { mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type APIRequestContext, type FrameLocator, type Page } from '@playwright/test'

import { resolve as resolveLine, ROOT } from './lines.mjs'
import { cut, hasLocalPath, PATH_RE } from './payload.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const STAGE = { width: 1920, height: 1080 }
const TYPE_DELAY_MS = 32
const TURN_TIMEOUT_MS = 15 * 60_000
const JOB_TIMEOUT_MS = 10 * 60_000

type PayloadSpec = { from: string; api?: string; pick?: string; limit?: number; fields?: string[]; head?: number }
type Turn = { question: string; shelf: string; dry_answer: string }
type Storyboard = {
  video: string
  provider: string
  models?: Record<string, string> | null
  banner: string
  providers?: Record<string, { banner: string; models: Record<string, string> | null }>
  mode?: 'flexible'
  hold?: number
  intake: Record<string, string>
  turns: Record<string, Turn>
  script: string[]
  rows: Row[]
}
type Row = {
  id: string
  scene: number
  subtitle: string
  turn?: string
  on: { step?: string; event?: string }
  payload?: PayloadSpec
  callouts?: string[][]
  slide?: string
  layer?: string
}
type Captured = { type: string; data: any; t_ms: number; turn: string | null; index: number }

const BOARD_FILE = 'storyboard-ollama.json'
const loadBoard = (): Storyboard => JSON.parse(readFileSync(join(HERE, BOARD_FILE), 'utf8'))
const CHAT_TYPES = new Set(['request', 'session', 'sources', 'token', 'done', 'error', 'answer'])

// ---------------------------------------------------------------- capture (all frames)

const CAPTURE = String.raw`(() => {
  if (location.pathname.startsWith('/__video')) return
  const send = (event) => window.__videoEvent(event)
  const parse = (block) => {
    let type = 'message'; const data = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) type = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (!data.length) return null
    try { return { type, data: JSON.parse(data.join('\n')) } } catch { return null }
  }
  // The app's JSON answers a row may show, copied as they arrive (never delayed).
  const KINDS = [
    ['intake', 'GET', /^\/api\/intake\/[^/]+$/, (d) => d.state === 'ready'],
    ['inspect', 'POST', /^\/api\/retrieve\/inspect$/, () => true],
    ['compare', 'GET', /^\/api\/eval\/compare/, () => true],
    ['rollback', 'POST', /^\/api\/documents\/\d+\/rollback$/, () => true],
  ]
  const original = window.fetch.bind(window)
  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url
    const path = new URL(url, location.href).pathname
    const method = (init.method || 'GET').toUpperCase()
    if (method === 'POST' && path === '/api/chat') {
      await send({ type: 'request', data: JSON.parse(init.body) })
      const response = await original(input, init)
      if (!response.ok || !response.body) return response
      const reader = response.body.getReader()
      const decoder = new TextDecoder(), encoder = new TextEncoder()
      const body = new ReadableStream({
        async start(controller) {
          let buffer = ''
          for (;;) {
            const { value, done } = await reader.read()
            buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n')
            let end
            while ((end = buffer.indexOf('\n\n')) !== -1) {
              const block = buffer.slice(0, end)
              buffer = buffer.slice(end + 2)
              const event = parse(block)
              if (event) await send(event)
              controller.enqueue(encoder.encode(block + '\n\n'))
            }
            if (done) break
          }
          const rest = parse(buffer.trim())
          if (rest) { await send(rest); controller.enqueue(encoder.encode(buffer.trim() + '\n\n')) }
          controller.close()
        },
      })
      return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers })
    }
    const response = await original(input, init)
    const kind = KINDS.find(([, m, re]) => m === method && re.test(path))
    if (kind && response.ok) {
      response.clone().json().then((data) => { if (kind[3](data)) send({ type: 'api', data: { api: kind[0], path, body: data } }) }).catch(() => {})
    }
    return response
  }
})()`

// ---------------------------------------------------------------- the conductor

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

// A subtitle stays at least this long per character, whatever the hold factor (hl-bead-studio F13).
const READ_MS_PER_CHAR = 1000 / 17

function holdMs(row: Row, factor = 1) {
  const chars = (row.subtitle || '').length
  const paced = (Math.min(Math.max(1400 + chars * 48, 2800), 8500) + (row.payload ? 1800 : 0)) * factor
  return Math.round(Math.max(paced, chars * READ_MS_PER_CHAR))
}

/**
 * Each row is shown once: an `on.event` row at the first matching event of its turn (every
 * row that matches, in storyboard order), an `on.step` row when the take reaches that step.
 * A row that never matched is reported in take.json, not failed.
 */
class Conductor {
  rows: Row[]
  shownIds = new Set<string>()
  t0 = 0
  turn: string | null = null
  events: Captured[] = []
  shown: Array<{ id: string; t_ms: number; hold_ms: number; subtitle: string; payload?: unknown; source?: unknown }> = []
  waits: Array<{ from_ms: number; to_ms: number; what: string }> = []
  inspects: Record<string, any> = {}
  answers: Record<string, any> = {}
  apis: Record<string, Captured> = {}
  sessionId: number | null = null
  failure: Error | null = null
  readonly failed: Promise<never>
  private reject: (err: Error) => void = () => {}
  private chain: Promise<void> = Promise.resolve()
  private turnDone: Promise<void> = Promise.resolve()
  private finishTurn: () => void = () => {}

  constructor(
    private page: Page,
    private api: APIRequestContext,
    private outDir: string,
    readonly board: Storyboard,
    private shelfIds: Record<string, number>,
  ) {
    this.failed = new Promise<never>((_, reject) => (this.reject = reject))
    this.failed.catch(() => {}) // observed through until()
    let turn: string | undefined
    this.rows = board.rows.map((row) => {
      const typed = row.on.step?.startsWith('typed:') ? row.on.step.slice(6) : undefined
      turn = typed ?? turn
      return { ...row, turn: row.turn ?? (row.on.event && CHAT_TYPES.has(row.on.event) ? turn : undefined) }
    })
  }

  setFailure(err: Error) {
    if (!this.failure) {
      this.failure = err
      this.reject(err)
    }
  }

  private fail(message: string): never {
    this.setFailure(new Error(message))
    throw this.failure
  }

  /** `p`, or the take's first failure, or a timeout. */
  async until<T>(p: Promise<T>, ms = TURN_TIMEOUT_MS, what = 'the app'): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${what}: nothing after ${ms / 1000} s`)), ms)
    })
    try {
      return await Promise.race([p, this.failed, timeout])
    } finally {
      clearTimeout(timer)
    }
  }

  check() {
    if (this.failure) throw this.failure
  }

  now() {
    return Date.now() - this.t0
  }

  beginTurn(key: string) {
    this.turn = key
    this.turnDone = new Promise((r) => (this.finishTurn = r))
  }

  async waitTurn() {
    await this.turnDone
    await this.chain
    this.check()
  }

  async idle() {
    await this.chain
    this.check()
  }

  /** The next api event of `kind` after `after` (an index into events). */
  async apiEvent(kind: string, after: number, ms = JOB_TIMEOUT_MS) {
    const deadline = Date.now() + ms
    for (;;) {
      const ev = this.events.find((e) => e.index >= after && e.type === 'api' && e.data.api === kind)
      if (ev) return ev
      this.check()
      if (Date.now() > deadline) this.fail(`no ${kind} answer from the app within ${ms / 1000} s`)
      await sleep(200)
    }
  }

  private matches(row: Row, ev: Captured) {
    if (!row.on.event || row.on.event !== ev.type) return false
    return !row.turn || row.turn === ev.turn
  }

  private payloadFor(row: Row, ev?: Captured) {
    const spec = row.payload
    if (!spec) return undefined
    let value: any
    let source: any
    let label: string
    if (spec.from === 'event') {
      if (!ev) this.fail(`row ${row.id}: payload from an event, but no event triggered it`)
      value = cut(ev.data, spec)
      source = { spec, index: ev.index }
      label = `SSE event: ${ev.type}`
    } else if (spec.from === 'inspect') {
      const inspect = this.inspects[row.turn!] ?? this.fail(`row ${row.id}: no retrieval inspection for turn "${row.turn}"`)
      value = cut(inspect, spec)
      source = { spec, turn: row.turn }
      label = 'POST /api/retrieve/inspect (the same search)'
    } else if (spec.from === 'answer') {
      const answer = this.answers[row.turn!] ?? this.fail(`row ${row.id}: no answer for turn "${row.turn}"`)
      value = cut(answer, spec)
      source = { spec, turn: row.turn }
      label = 'the stream, and the answer as stored'
    } else if (spec.from === 'api') {
      const ev = this.apis[spec.api!] ?? this.fail(`row ${row.id}: the app sent no ${spec.api} answer`)
      value = cut(ev.data.body, spec)
      source = { spec, index: ev.index }
      label = `${ev.data.path.startsWith('/api/retrieve') || ev.data.path.includes('rollback') ? 'POST' : 'GET'} ${ev.data.path.replace(/\?.*/, '')}`
    } else {
      this.fail(`row ${row.id}: unknown payload source "${spec.from}"`)
    }
    if (hasLocalPath(value)) this.fail(`row ${row.id}: the payload shows a local path`)
    const note = [spec.api, spec.pick].filter(Boolean).join('.') || 'captured'
    return { label: label!, note, value, source }
  }

  private async show(row: Row, ev?: Captured) {
    this.shownIds.add(row.id)
    const callouts = (row.callouts ?? []).map(([file, symbol]) => resolveLine(file, symbol))
    const payload = this.payloadFor(row, ev)
    const slideData = row.slide === 'end' ? this.endCard() : undefined
    const cue = { id: row.id, subtitle: row.subtitle, layer: row.layer, callouts, payload, slide: row.slide, slideData }
    await this.page.evaluate((c) => (window as any).stage.show(c), cue)
    const hold = holdMs(row, this.board.hold)
    this.shown.push({ id: row.id, t_ms: this.now(), hold_ms: hold, subtitle: row.subtitle, payload: payload?.value, source: payload?.source })
    await sleep(hold)
  }

  private endCard() {
    return {
      repo: process.env.VIDEO_REPO_URL || 'github.com/carlosgild-web/local-rag-ollama',
      author: process.env.VIDEO_AUTHOR ?? 'Carlos Velazquez',
      linkedin: process.env.VIDEO_LINKEDIN ?? 'linkedin.com/in/carlos-v-90b99149',
    }
  }

  /** Called by the page (exposeBinding) for every captured event; returning releases it. */
  async onEvent(raw: { type: string; data: any }) {
    const ev: Captured = { ...raw, t_ms: this.now(), turn: CHAT_TYPES.has(raw.type) ? this.turn : null, index: this.events.length }
    this.events.push(ev)
    if (ev.type === 'api') {
      this.apis[ev.data.api] = ev
      return
    }
    try {
      await this.chain
      if (this.failure) return
      if (ev.type === 'session') this.sessionId = ev.data.session_id
      // Before its rows: how the inspector ranks this turn's search, checked against what came.
      if (ev.type === 'sources') await this.inspect(ev)
      const rows = this.rows.filter((r) => !this.shownIds.has(r.id) && this.matches(r, ev))
      if (ev.type === 'error') {
        this.finishTurn()
        this.fail(`turn "${this.turn}" ended with an error: ${ev.data?.detail}`)
      }
      this.chain = (async () => {
        await sleep(250) // the app renders the event first
        for (const r of rows) await this.show(r, ev)
        if (ev.type === 'done') await this.onDone()
      })().catch((err) => {
        this.setFailure(err)
        this.finishTurn()
      })
    } catch (err) {
      this.setFailure(err as Error)
      this.finishTurn()
    }
  }

  /** The retrieval inspector on the turn's own question and shelf: the same search, read only. */
  private async inspect(ev: Captured) {
    const turn = this.board.turns[this.turn!]
    const response = await this.api.post('/api/retrieve/inspect', {
      data: { question: turn.question, scope: 'shelf', collection_id: this.shelfIds[turn.shelf], include_prompt: true },
    })
    expect(response.ok(), 'POST /api/retrieve/inspect').toBe(true)
    const inspect = await response.json()
    const sent = inspect.chunks.filter((c: any) => c.sent).map((c: any) => c.chunk_id)
    const came = ev.data.map((s: any) => s.chunk_id)
    if (JSON.stringify(sent) !== JSON.stringify(came)) this.fail(`turn "${this.turn}": the inspector ranks ${sent}, the chat sent ${came}`)
    this.inspects[this.turn!] = inspect
    writeFileSync(join(this.outDir, `inspect-${this.turn}.json`), JSON.stringify(inspect, null, 2))
  }

  /** The answer as streamed and as stored (after citation repair), then its rows. */
  private async onDone() {
    const turn = this.turn!
    const response = await this.api.get(`/api/sessions/${this.sessionId}`)
    expect(response.ok(), `GET /api/sessions/${this.sessionId}`).toBe(true)
    const session = await response.json()
    writeFileSync(join(this.outDir, `session-${turn}.json`), JSON.stringify(session, null, 2))
    const stored = [...session.messages].reverse().find((m: any) => m.role === 'assistant')
    const streamed = this.events.filter((e) => e.turn === turn && e.type === 'token').map((e) => e.data.text).join('')
    const answer = { model_wrote: streamed, stored: stored.content, citation_status: stored.citation_status }
    this.answers[turn] = answer
    const ev: Captured = { type: 'answer', data: answer, t_ms: this.now(), turn, index: this.events.length }
    this.events.push(ev)
    for (const r of this.rows.filter((r) => !this.shownIds.has(r.id) && this.matches(r, ev))) await this.show(r, ev)
    this.finishTurn()
  }

  /** The spec reached `name`: show its rows, if the storyboard has any. */
  async step(name: string) {
    await this.idle()
    for (const row of this.rows.filter((r) => r.on.step === name && !this.shownIds.has(r.id))) await this.show(row)
  }

  /** A wait the take sat through (a job, the analysis): compose.mjs cuts it with its real length. */
  async timed<T>(what: string, p: Promise<T>) {
    const from = this.now()
    const out = await p
    this.waits.push({ from_ms: from, to_ms: this.now(), what })
    return out
  }

  missing() {
    return this.rows.filter((r) => !this.shownIds.has(r.id)).map((r) => r.id)
  }
}

// ---------------------------------------------------------------- shared setup

async function guard(api: APIRequestContext) {
  const hint = 'Start the replay server (video/README.md), then run this again.'
  let demo: any
  try {
    demo = await api.get('/api/demo', { timeout: 5_000 }).then((r) => r.json())
  } catch {
    throw new Error(`The app is not running at ${test.info().project.use.baseURL}. ${hint}`)
  }
  if (!demo.documents) throw new Error(`The app has no documents: the demo company isn't loaded. ${hint}`)
}

/** The two evaluation runs the scene compares, made before the take (retrieval only, bge-m3). */
async function evalRuns(api: APIRequestContext) {
  const demo = await api.get('/api/eval/demo').then((r) => r.json())
  if (!demo.loaded_set_id) throw new Error('The demo golden set is not loaded (start.cmd video loads it).')
  // One at a time: the app refuses a run while another is in progress.
  const runs: number[] = []
  for (const [mode, label] of [['vector', 'vectors only'], ['hybrid', 'hybrid (the default)']]) {
    const response = await api.post('/api/eval/runs', { data: { eval_set_id: demo.loaded_set_id, mode, label } })
    if (!response.ok()) throw new Error(`POST /api/eval/runs (${mode}): ${response.status()} ${await response.text()}`)
    const { id } = await response.json()
    const deadline = Date.now() + JOB_TIMEOUT_MS
    for (;;) {
      const run = await api.get(`/api/eval/runs/${id}`).then((r) => r.json())
      if (run.status === 'completed') break
      if (run.status !== 'pending' && run.status !== 'running') throw new Error(`evaluation run ${id} ${run.status}: ${run.error}`)
      if (Date.now() > deadline) throw new Error(`evaluation run ${id} still ${run.status} after ${JOB_TIMEOUT_MS / 60_000} min`)
      await sleep(3000)
    }
    runs.push(id)
  }
  return runs
}

async function openStage(browser: import('@playwright/test').Browser, baseURL: string, outDir: string, onEvent?: (e: any) => Promise<void>) {
  const context = await browser.newContext({ baseURL, viewport: STAGE, recordVideo: { dir: join(outDir, 'raw'), size: STAGE } })
  await context.route('**/__video/*', (route) => {
    const name = new URL(route.request().url()).pathname.split('/').pop()!
    if (!['stage.html', 'stage.js'].includes(name)) return route.fulfill({ status: 404 })
    return route.fulfill({ path: join(HERE, name), contentType: name.endsWith('.js') ? 'text/javascript' : 'text/html' })
  })
  await context.addInitScript(CAPTURE)
  await context.exposeBinding('__videoEvent', async (_source, event) => (onEvent ? onEvent(event) : undefined))
  const t0 = Date.now()
  const page = await context.newPage()
  // "Restore this version" asks the browser to confirm: the take says yes.
  page.on('dialog', (dialog) => dialog.accept())
  await page.goto('/__video/stage.html')
  const app = page.frameLocator('#app')
  return { context, page, app, t0 }
}

let noticeChecked = false

async function loadApp(page: Page, app: FrameLocator, path: string) {
  await page.evaluate((p) => (window as any).stage.loadApp(p), path)
  // The console's notice (on the 7.2 GB laptop: qwen2.5:3b wouldn't fit next to the browser,
  // true in pass 2 where it isn't loaded) is about the machine, not the scene: its own ×.
  // Hidden once, it stays hidden for the visit, so only the first page waits for it.
  if (noticeChecked) return
  noticeChecked = true
  const hide = app.getByTitle('Hide until the next visit')
  if (await hide.waitFor({ timeout: 6_000 }).then(() => true, () => false)) await hide.click()
}

/** The page paints: an animation frame within 5 s; a stall is logged as a wait (luna F9, F11). */
async function waitPainting(page: Page, conductor: Conductor, where: string) {
  const frame = () =>
    page.evaluate(
      () => new Promise<boolean>((r) => { const t = setTimeout(() => r(false), 5000); requestAnimationFrame(() => { clearTimeout(t); r(true) }) }),
    )
  if (await frame()) return
  const from = conductor.now() - 5000
  const deadline = Date.now() + 180_000
  while (Date.now() < deadline) {
    if (await frame()) {
      conductor.waits.push({ from_ms: from, to_ms: conductor.now(), what: 'the browser catching up (low memory)' })
      return
    }
  }
  throw new Error(`${where}: the browser stopped painting for over 3 min (out of memory?)`)
}

async function assertNoPaths(page: Page, where: string) {
  const text: string = await page.evaluate(() => (window as any).stage.appText())
  const hit = text.match(PATH_RE)
  if (hit) throw new Error(`${where}: a local path is visible in the app ("${hit[0]}")`)
}

async function saveTake(conductor: Conductor, page: Page, context: import('@playwright/test').BrowserContext, outDir: string, extra: Record<string, unknown>) {
  writeFileSync(join(outDir, 'events.json'), JSON.stringify(conductor.events, null, 2))
  writeFileSync(join(outDir, 'shown.json'), JSON.stringify(conductor.shown, null, 2))
  writeFileSync(join(outDir, 'waits.json'), JSON.stringify(conductor.waits, null, 2))
  const take = {
    storyboard: BOARD_FILE,
    mode: conductor.board.mode ?? 'flexible',
    provider: conductor.board.provider,
    models_allowed: conductor.board.models ? Object.keys(conductor.board.models) : null,
    inspected: Object.keys(conductor.inspects),
    answered: Object.keys(conductor.answers),
    missing: conductor.missing(),
    failure: conductor.failure?.message ?? null,
    // Two passes (decision 0043): the folder of pass 1's runs that the app replayed.
    replay_of: process.env.VIDEO_REPLAY_DIR ?? null,
    ...extra,
  }
  writeFileSync(join(outDir, 'take.json'), JSON.stringify(take, null, 2))
  const video = page.video()
  await context.close()
  if (video) {
    await video.saveAs(join(outDir, 'take.webm.part'))
    renameSync(join(outDir, 'take.webm.part'), join(outDir, 'take.webm'))
  }
  rmSync(join(outDir, 'raw'), { recursive: true, force: true })
}

/** The files of one of the storyboard's intake folders, as capture.py uploads them. */
function files(board: Storyboard, key: string) {
  const dir = join(ROOT, board.intake[key])
  return readdirSync(dir)
    .map((f) => join(dir, f))
    .filter((f) => statSync(f).isFile())
    .sort()
}

// ---------------------------------------------------------------- the takes

test('smoke: the stage at 1920x1080 @smoke', async ({ browser, baseURL, request }) => {
  const outDir = join(HERE, 'out', 'smoke')
  mkdirSync(outDir, { recursive: true })
  const board = loadBoard()
  const demo = await request.get('/api/demo').then((r) => r.json())
  const { context, page, app } = await openStage(browser, baseURL!, outDir)
  await page.evaluate((b) => (window as any).stage.init(b), { banner: 'Smoke test: the stage layout', provider: `${demo.documents} documents` })
  await loadApp(page, app, '/chat')
  const row = board.rows.find((r) => r.id === '2.2')!
  const callouts = row.callouts!.map(([f, s]) => resolveLine(f, s))
  await page.evaluate((c) => (window as any).stage.show(c), {
    id: row.id, subtitle: row.subtitle, layer: row.layer, callouts,
    payload: { label: 'GET /api/demo', note: 'captured', value: demo },
  })
  const box = async (sel: string) => page.locator(sel).boundingBox()
  expect(await box('#app')).toEqual({ x: 0, y: 0, width: 1280, height: 960 })
  expect(await box('#panel')).toEqual({ x: 1280, y: 0, width: 640, height: 960 })
  expect(await box('#subs')).toEqual({ x: 0, y: 960, width: 1920, height: 120 })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > 1920 || document.documentElement.scrollHeight > 1080)
  expect(overflow, 'the stage scrolls').toBe(false)
  const pipelineFits = await page.evaluate(() => {
    const p = document.getElementById('pipeline')!
    return p.scrollWidth <= p.clientWidth
  })
  expect(pipelineFits, 'the pipeline fits the panel').toBe(true)
  await sleep(3_000)
  await page.screenshot({ path: join(outDir, 'stage.png') })
  await page.evaluate(() => (window as any).stage.slide('hook'))
  await sleep(2_000)
  await page.screenshot({ path: join(outDir, 'hook.png') })
  await page.evaluate(() => (window as any).stage.slide('end', { repo: 'github.com/carlosgild-web/local-rag-ollama', author: 'Carlos Velazquez', linkedin: 'linkedin.com/in/carlos-v-90b99149' }))
  await sleep(1_000)
  await page.screenshot({ path: join(outDir, 'end.png') })
  const video = page.video()
  await context.close()
  await video?.saveAs(join(outDir, 'smoke.webm'))
  rmSync(join(outDir, 'raw'), { recursive: true, force: true })
})

/**
 * The take, on pass 1's answers (the published video) or on scripted ones (a dry run of the
 * same steps, replay_server.py --dry). The script's order: the intake, three questions, the
 * new version and a fourth question, then the rollback, the inspector and the evaluation.
 */
for (const [provider, tag] of [['ollama', '@ollama'], ['dry', '@dry']] as const)
  test(`${provider} take ${tag}`, async ({ browser, baseURL, request }) => {
    test.setTimeout(90 * 60_000)
    const dry = provider === 'dry'
    const base = loadBoard()
    const board: Storyboard = { ...base, provider, ...(dry ? base.providers?.dry ?? {} : {}) }
    const outDir = join(HERE, 'out', dry ? 'dry' : 'ollama')
    rmSync(outDir, { recursive: true, force: true })
    mkdirSync(outDir, { recursive: true })
    await guard(request)
    const profiles = await request.get('/api/profiles').then((r) => r.json())
    const model = profiles.find((p: any) => p.is_active)?.chat_model ?? profiles[0]?.chat_model
    if (board.models && !(model in board.models)) throw new Error(`the app answers with ${model}, not one of the storyboard's models`)
    const [vectorRun, hybridRun] = await evalRuns(request)
    const shelves = await request.get('/api/collections').then((r) => r.json())
    const shelfIds: Record<string, number> = Object.fromEntries(shelves.filter((c: any) => c.is_active).map((c: any) => [c.name, c.id]))

    let conductor!: Conductor
    const { context, page, app, t0 } = await openStage(browser, baseURL!, outDir, (e) => conductor.onEvent(e))
    conductor = new Conductor(page, context.request, outDir, board, shelfIds)
    conductor.t0 = t0
    const until = <T>(p: Promise<T>, ms?: number, what?: string) => conductor.until(p, ms, what)
    let posterMs: number | null = null
    const script: string[] = []
    page.on('crash', () => conductor.setFailure(new Error('the page crashed (out of memory?)')))

    const box = app.getByPlaceholder(/Ask about your documents/)
    const chooseShelf = async (name: string) => {
      await app.getByLabel('Shelf to search').selectOption({ label: name })
      await sleep(500)
    }
    const ask = async (key: string) => {
      script.push(`ask:${key}`)
      await waitPainting(page, conductor, `before "${key}"`)
      await box.click()
      conductor.beginTurn(key)
      // The row comes up as the typing starts, so the last scene's subtitle doesn't linger.
      const typedRow = conductor.step(`typed:${key}`)
      await box.pressSequentially(board.turns[key].question, { delay: TYPE_DELAY_MS })
      await typedRow
      await box.press('Enter')
      await until(conductor.waitTurn(), TURN_TIMEOUT_MS, `turn "${key}"`)
      await waitPainting(page, conductor, `after "${key}"`)
      await expect(app.getByTitle('Send')).toBeVisible()
      await sleep(600)
    }
    /** Library → choose the folder's files → the suggestions; returns the confirm button. */
    const addFiles = async (key: string, pickStep?: string) => {
      script.push(`intake:${key}`)
      await loadApp(page, app, '/library')
      const choose = app.getByRole('button', { name: /Choose files/ })
      await expect(choose).toBeEnabled()
      await choose.hover()
      if (pickStep) await conductor.step(pickStep)
      await app.locator('input[type="file"]:not([webkitdirectory])').setInputFiles(files(board, key))
      await sleep(800)
      const analyze = app.getByRole('button', { name: /^Analyze \d+ document/ })
      await analyze.hover()
      await sleep(500)
      const from = conductor.events.length
      await analyze.click()
      await conductor.timed(
        'reading and embedding the files (bge-m3)',
        until(expect(app.getByRole('heading', { name: 'Suggested shelves and tags' })).toBeVisible({ timeout: JOB_TIMEOUT_MS }), JOB_TIMEOUT_MS, 'the analysis'),
      )
      await conductor.apiEvent('intake', from)
      await sleep(900)
      return app.getByRole('button', { name: /^(Create \d+ shel|Process \d+ document)/ })
    }
    const confirm = async (button: import('@playwright/test').Locator) => {
      await button.scrollIntoViewIfNeeded()
      await button.hover()
      await sleep(600)
      await button.click()
      await conductor.timed(
        'indexing (bge-m3, Chroma, SQLite FTS5)',
        until(expect(app.getByText(/^Done: \d+ indexed/)).toBeVisible({ timeout: JOB_TIMEOUT_MS }), JOB_TIMEOUT_MS, 'the indexing'),
      )
      await sleep(1200)
    }

    try {
      const models = Object.entries(board.models ?? {})
      await page.evaluate((b) => (window as any).stage.init(b), {
        banner: models.length ? board.banner.replace('{model}', models[0][1]) : board.banner,
        provider: '',
      })
      await conductor.step('hook')

      // Scene 1: adding files (the slide has been held; the app comes up under it)
      await page.evaluate(() => (window as any).stage.hideSlide())
      const process1 = await addFiles('showcase', 'intake:pick')
      await conductor.step('intake:suggested')
      await app.getByText('Please check').first().scrollIntoViewIfNeeded().catch(() => {})
      await confirm(process1)
      await conductor.step('intake:indexed')
      await assertNoPaths(page, 'intake')

      // Scenes 2-4: a cited answer, its passage, and "not found"
      await loadApp(page, app, '/chat')
      await chooseShelf('hr')
      await ask('holiday')
      const cite = app.locator('button[title*="05-holiday-announcement"]').first()
      if (await cite.isVisible().catch(() => false)) {
        await cite.hover()
        await sleep(400)
        await cite.click()
        await app.getByText('December 22', { exact: false }).last().evaluate((el) => {
          const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
          for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const text = node.textContent ?? ''
            const at = text.indexOf('December 22')
            if (at < 0) continue
            const end = text.indexOf('\n', at)
            const range = document.createRange()
            range.setStart(node, at)
            range.setEnd(node, end < 0 ? text.length : end)
            const mark = document.createElement('mark')
            mark.style.cssText = 'background: rgba(250, 204, 21, .45); color: inherit; border-radius: 3px; padding: 0 2px'
            range.surroundContents(mark)
            mark.scrollIntoView({ block: 'center' })
            return
          }
        }).catch(() => {}) // a real model may cite another passage: no mark then
        await sleep(600)
      }
      posterMs = conductor.now()
      await conductor.step('cite')
      await ask('dental')
      await assertNoPaths(page, 'chat')

      // Scene 5: a new version, and a rollback
      await app.getByRole('button', { name: 'New chat' }).click()
      await sleep(600)
      await chooseShelf('operations')
      await ask('returns')
      const process2 = await addFiles('v2', 'v2:pick')
      await conductor.step('v2:suggested')
      await confirm(process2)
      await loadApp(page, app, '/chat')
      await app.getByRole('button', { name: 'New chat' }).click()
      await sleep(400)
      await chooseShelf('operations')
      await ask('returns_v2')
      await loadApp(page, app, '/library')
      await app.getByRole('button', { name: '09-shipping-returns-policy.md' }).first().click()
      const versions = app.getByRole('button', { name: /^Versions \(\d+\)/ })
      await versions.hover()
      await sleep(500)
      await versions.click()
      const restore = app.getByRole('button', { name: /Restore this version/ }).first()
      await expect(restore).toBeVisible()
      await restore.scrollIntoViewIfNeeded()
      await restore.hover()
      await sleep(700)
      const before = conductor.events.length
      await restore.click()
      await conductor.apiEvent('rollback', before, 30_000)
      await sleep(900)
      await conductor.step('rollback')
      await assertNoPaths(page, 'versions')

      // Scene 6: the retrieval inspector
      await loadApp(page, app, '/inspector')
      await app.getByLabel('Shelf').selectOption({ label: 'hr' })
      const question = app.locator('#inspect-question')
      await question.click()
      await question.fill(board.turns.holiday.question) // typed twice already in the chat
      let mark = conductor.events.length
      await app.getByRole('button', { name: 'Inspect', exact: true }).click()
      await conductor.apiEvent('inspect', mark, 120_000)
      await sleep(1500)
      await conductor.step('inspector')
      const weight = app.locator('label', { hasText: 'Vector weight' }).locator('input[type="range"]')
      await weight.scrollIntoViewIfNeeded()
      await weight.hover()
      mark = conductor.events.length
      await weight.fill('1')
      await conductor.apiEvent('inspect', mark, 60_000)
      await sleep(1500)
      await conductor.step('inspector:weight')

      // Scene 7: the evaluation, two runs compared
      mark = conductor.events.length
      await loadApp(page, app, `/evaluation?a=${vectorRun}&b=${hybridRun}`)
      await conductor.apiEvent('compare', mark, 60_000)
      await sleep(1500)
      await conductor.step('eval')
      await conductor.step('eval:b')
      await assertNoPaths(page, 'evaluation')

      await conductor.step('end')
      await sleep(1000)
      conductor.check()
      // Pass 1 followed the same script: otherwise the prompts (and the replay) would differ.
      if (JSON.stringify(script) !== JSON.stringify(board.script))
        throw new Error(`the take's steps ${script} differ from the storyboard's script ${board.script}`)
    } finally {
      await saveTake(conductor, page, context, outDir, { poster_ms: posterMs, script, model, eval_runs: [vectorRun, hybridRun] })
    }
  })
