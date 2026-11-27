import { spawnSync } from 'node:child_process'
import { mkdirSync, readdirSync, rmSync } from 'node:fs'
import { join } from 'node:path'

import { type BrowserContext, expect, type Page, test } from '@playwright/test'

/**
 * The README's GIFs and the chat screenshots (Phase 10, decision 0042), on harness.py: the
 * real app on Ollama's bge-m3 with qwen2.5:3b's answers replayed from a recorded run.
 * `npm run showcase` writes docs/showcase/demo.gif, docs/showcase/img/intake-flow.gif and
 * the screenshots in docs/showcase/img/ (the GIFs need ffmpeg on the PATH; without it the
 * WebM is kept). With E2E_RECORD=1 the same steps run on the real model and refresh
 * replay.json. Not part of CI.
 */

const DOCS = join('..', '..', 'docs', 'showcase')
const IMG = join(DOCS, 'img')
const VIDEO_DIR = join(DOCS, '.gif-video')
const SIZE = { width: 1280, height: 800 }
const RECORD = process.env.E2E_RECORD === '1'

const QUESTION = 'When does the company close for the holidays?'
const NOT_IN_DOCS = 'What dental insurance coverage do employees get?'
const INTAKE = ['2027-trade-show-planning-notes.txt', 'cristal-dorado-price-update-2027.md', 'kiln-maintenance-log.txt'].map(
  (f) => join('intake', f),
)

/**
 * The console's top notice (on the 7.2 GB laptop, the low-memory warning) is about the
 * machine, not the flow: hide it with its own × before the GIF starts.
 */
async function hideNotice(page: Page) {
  // It appears once the health check answers, a moment after the page.
  const hide = page.getByTitle('Hide until the next visit')
  if (await hide.waitFor({ state: 'visible', timeout: 6000 }).then(() => true, () => false)) {
    await hide.click()
    await expect(hide).toBeHidden()
  }
}

test.describe.configure({ mode: 'serial' })

async function recorded(browser: import('@playwright/test').Browser, baseURL: string | undefined) {
  rmSync(VIDEO_DIR, { recursive: true, force: true })
  return browser.newContext({ baseURL, viewport: SIZE, recordVideo: { dir: VIDEO_DIR, size: SIZE } })
}

async function chooseShelf(page: Page, name: string) {
  await page.getByLabel('Shelf to search').selectOption({ label: name })
}

async function ask(page: Page, question: string) {
  const box = page.getByPlaceholder(/Ask about your documents/)
  await box.click()
  await box.pressSequentially(question, { delay: 45 })
  await page.waitForTimeout(400)
  await box.press('Enter')
  // Streaming shows a Stop button; the answer is saved when the Send button is back.
  await expect(page.getByTitle('Stop')).toBeVisible()
  await expect(page.getByTitle('Send')).toBeVisible()
  await page.waitForTimeout(500)
}

/** Marks the passage line that holds `start` (a highlight; the text is unchanged). */
async function markLine(page: Page, start: string) {
  await page.getByText(start, { exact: false }).last().evaluate((el, start) => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.textContent ?? ''
      const at = text.indexOf(start)
      if (at < 0) continue
      const end = text.indexOf('\n', at)
      const range = document.createRange()
      range.setStart(node, at)
      range.setEnd(node, end < 0 ? text.length : end)
      const mark = document.createElement('mark')
      mark.style.cssText = 'background: rgba(250, 204, 21, .45); color: inherit; border-radius: 3px; padding: 0 2px'
      range.surroundContents(mark)
      mark.scrollIntoView({ block: 'center', behavior: 'smooth' })
      return
    }
  }, start)
  await page.waitForTimeout(500)
}

async function shot(page: Page, name: string) {
  if (!RECORD) await page.screenshot({ path: join(IMG, `${name}.jpg`), type: 'jpeg', quality: 88 })
}

/** Seconds into the recording: [from, to] pieces kept in the GIF, in order. */
type Segment = [number, number]

/**
 * WebM → GIF of the given segments with the portfolio's README spec (10 fps, 960 px, a
 * palette of its own). Several segments are joined: a long real wait is cut, and the
 * README caption says so.
 */
function toGif(webm: string, gif: string, segments: Segment[], colors = 96) {
  const pieces = segments
    .map(([a, b], i) => `[0:v]trim=start=${a.toFixed(2)}:end=${b.toFixed(2)},setpts=PTS-STARTPTS[s${i}]`)
    .join(';')
  const joined = segments.map((_, i) => `[s${i}]`).join('') + `concat=n=${segments.length}:v=1:a=0[v]`
  const filters =
    `${pieces};${joined};[v]fps=10,scale=960:-1:flags=lanczos,split[a][b];` +
    `[a]palettegen=max_colors=${colors}:stats_mode=diff[p];` +
    '[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle'
  const run = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', webm, '-filter_complex', filters, '-loop', '0', gif], {
    timeout: 180_000,
    encoding: 'utf8',
  })
  if (run.error || run.status !== 0) {
    console.warn(`showcase: no GIF (${run.error?.message ?? run.stderr.trim()}); the WebM stays at ${webm}`)
    return false
  }
  return true
}

async function finish(context: BrowserContext, page: Page, gif: string, segments: Segment[], colors?: number) {
  const video = page.video()
  await context.close()
  if (RECORD || !video) return
  const webm = await video.path()
  const length = segments.reduce((sum, [a, b]) => sum + b - a, 0)
  const parts = segments.map(([a, b]) => `${a.toFixed(1)}-${b.toFixed(1)} s`).join(' + ')
  console.log(`showcase: ${gif} from ${parts} (${length.toFixed(1)} s)`)
  if (toGif(webm, gif, segments, colors)) rmSync(VIDEO_DIR, { recursive: true, force: true })
}

/**
 * The main GIF: the console chat → a question on the hr shelf → the answer streams with its
 * citations → the passage behind the holiday announcement's citation → a question the shelf
 * can't answer → "not found in the documents".
 */
test('main flow: a cited answer, its passage, and "not found"', async ({ browser, baseURL }) => {
  mkdirSync(IMG, { recursive: true })
  const context = await recorded(browser, baseURL)
  const page = await context.newPage()
  const t0 = Date.now()
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: 'Ask your documents' })).toBeVisible()
  await hideNotice(page)
  await chooseShelf(page, 'hr')
  await page.waitForTimeout(600)
  const startS = (Date.now() - t0) / 1000 - 0.2
  await page.waitForTimeout(1000)

  await ask(page, QUESTION)
  await page.waitForTimeout(2500)
  await shot(page, '07-chat-citations')

  // The citation that points at the holiday announcement, and its passage.
  await page.locator('button[title*="05-holiday-announcement"]').first().click()
  await expect(page.getByText(/December 22/).last()).toBeVisible()
  await markLine(page, 'December 22')
  await page.waitForTimeout(3000)
  await shot(page, '08-passage')

  await ask(page, NOT_IN_DOCS)
  await expect(page.getByText('not found in the documents').last()).toBeVisible()
  await page.waitForTimeout(3200)
  await shot(page, '09-not-found')
  const endS = (Date.now() - t0) / 1000
  await finish(context, page, join(DOCS, 'demo.gif'), [[startS, endS]], 64)
})

/**
 * The intake GIF: three new files → the app reads them and suggests a shelf and tags for
 * each (a new shelf named by the model) → confirm → indexed.
 */
test('intake flow: suggested shelves and tags, then confirm', async ({ browser, baseURL }) => {
  const context = await recorded(browser, baseURL)
  const page = await context.newPage()
  const t0 = Date.now()
  await page.goto('/library')
  await expect(page.getByRole('button', { name: /Choose files/ })).toBeEnabled()
  await hideNotice(page)
  await page.waitForTimeout(600)
  const startS = (Date.now() - t0) / 1000 - 0.2
  await page.waitForTimeout(1200)

  await page.getByRole('button', { name: /Choose files/ }).hover()
  await page.waitForTimeout(500)
  await page.locator('input[type="file"]:not([webkitdirectory])').setInputFiles(INTAKE)
  await page.waitForTimeout(1500)
  const analyze = page.getByRole('button', { name: /Analyze 3 documents/ })
  await analyze.hover()
  await page.waitForTimeout(500)
  await analyze.click()
  // The analysis embeds every file with bge-m3 (about 25 s on the laptop CPU): the GIF
  // shows its first seconds, then cuts to the suggestions.
  await page.waitForTimeout(2500)
  const cutFromS = (Date.now() - t0) / 1000

  await expect(page.getByRole('heading', { name: 'Suggested shelves and tags' })).toBeVisible()
  const cutToS = (Date.now() - t0) / 1000 - 0.3
  await page.waitForTimeout(3500)
  await shot(page, '04-suggestions')
  // The file the app isn't sure about: "please check", with the other shelf it fits.
  await page.getByText('Please check').first().scrollIntoViewIfNeeded()
  await page.getByText('Please check').first().hover()
  await page.waitForTimeout(3000)

  const confirm = page.getByRole('button', { name: /^(Create \d+ shel|Process \d+ document)/ })
  await confirm.scrollIntoViewIfNeeded()
  await confirm.hover()
  await page.waitForTimeout(800)
  await confirm.click()
  // The three files show up in the library once their jobs finish.
  await expect(page.getByText('kiln-maintenance-log.txt').first()).toBeVisible()
  await expect(page.getByText(/Processing \d+ files?/)).toHaveCount(0, { timeout: RECORD ? 300_000 : 120_000 })
  await page.waitForTimeout(3000)
  const endS = (Date.now() - t0) / 1000
  await finish(context, page, join(IMG, 'intake-flow.gif'), [[startS, cutFromS], [cutToS, endS]], 64)
})

test.afterAll(() => {
  // Playwright's own output folder; the GIF WebMs are removed after each conversion.
  for (const name of readdirSync('.')) if (name === 'test-results') rmSync(name, { recursive: true, force: true })
})
