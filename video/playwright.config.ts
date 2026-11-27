import { defineConfig } from '@playwright/test'

/**
 * The recorder drives the app that is already running; it never starts or stops it: the
 * replay server on data-video/ (port 8010), with pass 1's answers or, for a dry run, scripted
 * ones (video/README.md). The page is the 1920x1080 stage, which hosts the real app in an
 * iframe on the app's own origin.
 */
export default defineConfig({
  testDir: '.',
  testMatch: 'record.spec.ts',
  outputDir: 'out/test-results',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 40 * 60_000,
  // A model turn on a laptop CPU takes minutes.
  expect: { timeout: 60_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8010',
    channel: process.env.VIDEO_BROWSER_CHANNEL || 'msedge',
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
    colorScheme: 'light',
    locale: 'en-US',
    actionTimeout: 90_000,
    // A take waits minutes for the model. If the display turns off or locks, Windows' native
    // occlusion tracking marks Edge's (hidden) window occluded and it stops painting: the
    // first Ollama take of luna-hybrid-agent froze that way (its finding F9).
    launchOptions: { args: ['--disable-features=CalculateNativeWinOcclusion', '--disable-gpu'] },
  },
})
