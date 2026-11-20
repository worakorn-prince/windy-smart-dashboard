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

  test('process card excludes System Idle Process and keeps CPU percentages within 100', async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))
    await page.goto('/')

    const processCard = page.locator('[data-card-id="processes"]')
    const cpuValues = processCard.locator('.cpu-value')
    await expect(cpuValues.first()).toBeVisible()
    await expect(processCard).not.toContainText(/system idle process/i)

    const values = await cpuValues.allTextContents()
    expect(values.length).toBeGreaterThan(0)
    for (const value of values) {
      const percent = Number.parseFloat(value)
      expect(Number.isFinite(percent)).toBe(true)
      expect(percent).toBeGreaterThanOrEqual(0)
      expect(percent).toBeLessThanOrEqual(100)
    }
    expect(pageErrors).toEqual([])
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

test.describe('Insights page', () => {
  test('/insights shows sidebar entry and summary cards with real data', async ({ page }) => {
    await page.goto('/insights')

    await expect(page.getByTestId('side-nav-insights')).toBeVisible()
    await expect(page.getByTestId('insights-head')).toBeVisible()
    await expect(page.getByTestId('insights-range-tabs')).toBeVisible()

    const trends = page.getByTestId('insights-trends')
    await expect(trends).toBeVisible()
    // Insights cold start (first vite compile + backend compute under load) can
    // exceed the 10s default expect timeout; wait up to 30s for the data-driven
    // canvas like the drag test waits for the processes row.
    await expect(trends.locator('canvas').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId('insights-window-note')).toContainText(/samples/)

    await expect(page.getByTestId('insights-disk')).toBeVisible()
    await expect(page.getByTestId('insights-disk').locator('tbody tr').first()).toBeVisible()

    await expect(page.getByTestId('insights-processes')).toBeVisible()
    await expect(page.getByTestId('insights-processes').locator('tbody tr').first()).toBeVisible()
  })
})

test.describe('Card drag & drop', () => {
  test('dragging a card onto another swaps their positions and persists across reload', async ({ page }) => {
    // Cards grow once live metrics arrive; a fixed viewport can push the drop target
    // off-screen (elementFromPoint returns null), so size the viewport from the real
    // layout after data has loaded instead of hard-coding a height.
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
    // Cards grow once live metrics arrive (~1.8kpx above the disk slot); measuring
    // before that paints an empty (short) layout and the WS payload lands mid-drag,
    // moving the drop target. Wait for data before measuring anything.
    await expect(page.locator('[data-card-id="processes"] tbody tr').first()).toBeVisible()

    const from = await powerGrip.boundingBox()
    const to = await diskSlot.boundingBox()
    expect(from).not.toBeNull()
    expect(to).not.toBeNull()
    if (to && to.y + to.height > 1400) {
      // Grow the viewport so the drop target stays hit-testable, then re-measure
      // both endpoints in case the resize reflowed the layout.
      await page.setViewportSize({ width: 1280, height: Math.ceil(to.y + to.height + 100) })
      const refreshedFrom = await powerGrip.boundingBox()
      const refreshedTo = await diskSlot.boundingBox()
      expect(refreshedFrom).not.toBeNull()
      expect(refreshedTo).not.toBeNull()
      from!.x = refreshedFrom!.x
      from!.y = refreshedFrom!.y
      from!.width = refreshedFrom!.width
      from!.height = refreshedFrom!.height
      to.x = refreshedTo!.x
      to.y = refreshedTo!.y
      to.width = refreshedTo!.width
      to.height = refreshedTo!.height
    }

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
