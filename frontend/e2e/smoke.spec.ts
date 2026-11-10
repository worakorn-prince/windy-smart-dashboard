import { expect, test } from '@playwright/test'

const THEME_STORAGE_KEY = 'dash-theme'

test.describe('API smoke', () => {
  test('/api/version returns 200 with a semver version', async ({ request }) => {
    const response = await request.get('/api/version')
    expect(response.status()).toBe(200)

    const body = (await response.json()) as { name?: string; version?: string; port?: number }
    expect(body.name).toBe('windy-smart-dashboard')
    expect(body.version).toMatch(/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/)
    expect(typeof body.port).toBe('number')
  })
})

test.describe('Shell and dashboard', () => {
  test('brand, nav links and primary zone cards render', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByRole('link', { name: /Windy Smart Dashboard/ })).toBeVisible()

    const navLinks = page.locator('header.nav nav a')
    await expect(navLinks).toHaveCount(3)
    await expect(navLinks.nth(0)).toHaveText('Dashboard')
    await expect(navLinks.nth(1)).toHaveText('Security')
    await expect(navLinks.nth(2)).toHaveText('Maintenance')

    const primaryZone = page.locator('[data-testid="primary-zone"]')
    await expect(primaryZone).toBeVisible()
    expect(await primaryZone.locator('.card').count()).toBeGreaterThanOrEqual(3)
    await expect(page.locator('[data-testid="secondary-zone"]')).toBeVisible()
  })

  test('layout toolbar opens and closes the layout panel', async ({ page }) => {
    await page.goto('/')

    const panel = page.locator('[data-testid="layout-panel"]')
    await expect(panel).toHaveCount(0)

    await page.locator('[data-testid="layout-toggle"]').click()
    await expect(panel).toBeVisible()
    await expect(page.locator('[data-testid="layout-row-cpu"]')).toBeVisible()
    await expect(page.locator('[data-testid="layout-row-gpu"]')).toBeVisible()

    await page.locator('[data-testid="layout-toggle"]').click()
    await expect(panel).toHaveCount(0)
  })
})

test.describe('Theme toggle', () => {
  test('switches data-theme and persists across reload', async ({ page }) => {
    await page.goto('/')

    const html = page.locator('html')
    await expect(html).toHaveAttribute('data-theme', 'dark')

    await page.locator('[data-testid="theme-toggle"]').click()
    await expect(html).toHaveAttribute('data-theme', 'light')
    expect(await page.evaluate((key) => localStorage.getItem(key), THEME_STORAGE_KEY)).toBe('light')

    await page.reload()
    await expect(html).toHaveAttribute('data-theme', 'light')
    await expect(page.locator('[data-testid="theme-toggle"]')).toBeVisible()
  })
})

test.describe('Security and maintenance pages', () => {
  test('security page shows live events and event history headings', async ({ page }) => {
    await page.goto('/security')

    await expect(page.getByRole('heading', { name: /Live Security Events/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Security Event History/ })).toBeVisible()
  })

  test('maintenance page shows reports, startup and Windows Update sections', async ({ page }) => {
    await page.goto('/maintenance')

    await expect(page.getByRole('heading', { level: 2, name: /Maintenance/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Scheduled reports/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /เปิดพร้อม Windows/ })).toBeVisible()

    const wuCard = page.locator('[data-testid="windows-update-card"]')
    await expect(wuCard).toBeVisible()
    await expect(wuCard.locator('h3')).toContainText(/Windows Update/)
    await expect(wuCard.getByRole('button', { name: /Scan now/ })).toBeVisible()
    await expect(wuCard.getByTestId('pending-reboot-badge')).toBeVisible()
  })
})
