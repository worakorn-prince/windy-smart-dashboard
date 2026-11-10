import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const CONFIG_DIR = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(CONFIG_DIR, '..')
const BASE_URL = 'http://127.0.0.1:5173'
const BACKEND_URL = 'http://127.0.0.1:8000/api/version'

const backendCommand =
  process.platform === 'win32' ? '.venv\\Scripts\\python.exe backend\\main.py' : 'python3 backend/main.py'

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : 2,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      cwd: REPO_ROOT,
      command: backendCommand,
      url: BACKEND_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      cwd: CONFIG_DIR,
      command: 'npm run dev -- --host 127.0.0.1',
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
