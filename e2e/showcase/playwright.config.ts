import { existsSync } from 'node:fs'
import { join } from 'node:path'

import { defineConfig } from '@playwright/test'

/**
 * The README GIFs and screenshots (decision 0042): `npm run showcase`. One backend,
 * harness.py: the real app and the built web app on Ollama's bge-m3, with the chat
 * model's answers replayed from a recorded qwen2.5:3b run (E2E_RECORD=1 records them).
 * Edge, the browser already on Windows, so nothing is downloaded. Not part of CI.
 */
const PORT = Number(process.env.E2E_PORT ?? 8020)
const RECORD = process.env.E2E_RECORD === '1'
const venvPython = join('..', '..', 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const python = process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : 'python')

export default defineConfig({
  testDir: './tests',
  // A recording waits for the real model: about 35 s a question on the 7.2 GB laptop.
  timeout: RECORD ? 900_000 : 240_000,
  expect: { timeout: RECORD ? 300_000 : 60_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    channel: 'msedge',
    locale: 'en-US',
    viewport: { width: 1280, height: 800 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${python}" harness.py`,
    env: { E2E_PORT: String(PORT), E2E_RECORD: RECORD ? '1' : '0' },
    // The harness loads the demo company (11 documents through bge-m3) before it serves.
    url: `http://127.0.0.1:${PORT}/api/demo`,
    timeout: 900_000,
    reuseExistingServer: false,
  },
})
