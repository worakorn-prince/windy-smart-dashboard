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
    await expect(page.locator('[data-testid="side-nav-viewer"]')).toHaveCount(0)

    const primaryZone = page.locator('[data-testid="primary-zone"]')
    await expect(primaryZone).toBeVisible()
    expect(await primaryZone.locator('.card').count()).toBeGreaterThanOrEqual(3)
    await expect(page.locator('[data-testid="secondary-zone"]')).toBeVisible()
  })

  test('sidebar renders brand, grouped nav and device card', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByTestId('sidebar')).toBeVisible()
    await expect(page.getByTestId('side-nav')).toBeVisible()
    await expect(page.getByTestId('device-card')).toBeVisible()
    await expect(page.getByTestId('side-nav-dashboard')).toHaveClass(/is-active/)
  })

  test('dashboard shows page header and four KPI tiles', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByTestId('dashboard-head')).toBeVisible()
    await expect(page.getByTestId('stat-row')).toBeVisible()
    for (const label of ['cpu', 'gpu', 'ram', 'power']) {
      await expect(page.getByTestId(`stat-tile-${label}`)).toBeVisible()
    }
  })

  test('history card exposes the 5m range tab', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByTestId('history-tabs')).toBeVisible()
    await expect(page.locator('button', { hasText: '5 นาที' })).toBeVisible()
  })

  test('sidebar collapses to the icon rail on narrow screens', async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 900 })
    await page.goto('/')

    const sidebar = await page.getByTestId('sidebar').boundingBox()
    expect(sidebar).not.toBeNull()
    expect(sidebar!.width).toBeLessThan(100)
    await expect(page.getByTestId('side-nav-dashboard')).toBeVisible()

    const content = await page.locator('main.content').boundingBox()
    expect(content).not.toBeNull()
    expect(content!.x).toBeGreaterThanOrEqual(60)
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

    await expect(page.getByRole('heading', { level: 1, name: /บำรุงรักษาระบบ/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Scheduled reports/ })).toBeVisible()
    await expect(page.getByRole('heading', { name: /เปิดพร้อม Windows/ })).toBeVisible()

    const wuCard = page.locator('[data-testid="windows-update-card"]')
    await expect(wuCard).toBeVisible()
    await expect(wuCard.locator('h3')).toContainText(/Windows Update/)
    await expect(wuCard.getByRole('button', { name: /Scan now/ })).toBeVisible()
    await expect(wuCard.getByTestId('pending-reboot-badge')).toBeVisible()
  })
})

test.describe('Card drag & drop', () => {
  test('dragging a card onto another swaps their positions and persists across reload', async ({ page }) => {
    // 720px-tall default viewport clips the disk card (elementFromPoint returns null off-screen),
    // so use a taller viewport to keep both cards hit-testable during the drag.
    await page.setViewportSize({ width: 1280, height: 1400 })
    await page.goto('/')

    const powerGrip = page.locator('[data-card-id="power"] .drag-grip')
    const diskSlot = page.locator('[data-card-id="disk"]')
    await expect(powerGrip).toBeVisible()
    await expect(diskSlot).toBeVisible()

    const before = await page.evaluate(() => {
      const raw = localStorage.getItem('dash:layout:v1')
      return raw ? JSON.parse(raw) : null
    })
    if (before?.order && before.order.indexOf('disk') < before.order.indexOf('power')) {
      await page.evaluate(() => localStorage.removeItem('dash:layout:v1'))
      await page.reload()
      await expect(page.locator('[data-card-id="power"] .drag-grip')).toBeVisible()
    }

    const from = await powerGrip.boundingBox()
    const to = await diskSlot.boundingBox()
    expect(from).not.toBeNull()
    expect(to).not.toBeNull()

    await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2)
    await page.mouse.down()
    await page.mouse.move(to!.x + to!.width / 2, to!.y + to!.height / 2, { steps: 25 })
    await page.mouse.up()

    const after = await page.evaluate(() => {
      const raw = localStorage.getItem('dash:layout:v1')
      return raw ? JSON.parse(raw) : null
    })
    expect(after).not.toBeNull()
    expect(after.order.indexOf('disk')).toBeLessThan(after.order.indexOf('power'))
    expect(after.order.indexOf('power')).toBeGreaterThan(after.order.indexOf('disk'))

    await page.reload()

    const afterReload = await page.evaluate(() => {
      const raw = localStorage.getItem('dash:layout:v1')
      return raw ? JSON.parse(raw) : null
    })
    expect(afterReload).toEqual(after)

    await expect(page.locator('[data-testid="secondary-zone"] .card-slot').first()).toHaveAttribute(
      'data-card-id',
      'disk',
    )
  })
})
