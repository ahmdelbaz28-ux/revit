/**
 * V192 Visual Smoke Test — Life-safety system verification.
 *
 * Tests that EVERY page loads without console errors and has the expected
 * key UI elements. This is a smoke test, not a full visual regression —
 * but it catches the most critical issues (page crashes, missing elements,
 * console errors) automatically.
 *
 * Per agent.md Rule 10: tests exist to expose defects. These tests will
 * FAIL if any page has console errors or is missing critical elements.
 */
import { test, expect } from '@playwright/test';

const PAGES = [
  { route: '/', name: 'Dashboard', criticalElements: ['h1', 'button'] },
  { route: '/projects', name: 'Projects', criticalElements: ['h1', 'button', 'table'] },
  { route: '/elements', name: 'Elements', criticalElements: ['h1', 'button', 'table'] },
  { route: '/connections', name: 'Connections', criticalElements: ['h1', 'button', 'table'] },
  { route: '/conflicts', name: 'Conflicts', criticalElements: ['h1', 'button'] },
  { route: '/engineering', name: 'Engineering', criticalElements: ['h1', 'button'] },
  { route: '/fire-alarm', name: 'FireAlarm', criticalElements: ['h1', 'button', 'svg'] },
  { route: '/reports', name: 'Reports', criticalElements: ['h1', 'button'] },
  { route: '/autocad', name: 'AutoCAD', criticalElements: ['h1', 'button'] },
  { route: '/revit', name: 'Revit', criticalElements: ['h1', 'button'] },
  { route: '/digital-twin', name: 'DigitalTwin', criticalElements: ['h1', 'button'] },
  { route: '/settings', name: 'Settings', criticalElements: ['h1', 'button'] },
];

for (const { route, name, criticalElements } of PAGES) {
  test(`${name} page loads without console errors`, async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Skip CSP warnings (these are dev-server artifacts, not real errors)
        if (text.includes('frame-ancestors') || text.includes('X-Frame-Options')) {
          return;
        }
        errors.push(text);
      }
    });

    await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(1500);

    // Verify critical elements exist
    for (const selector of criticalElements) {
      const count = await page.locator(selector).count();
      expect(count, `${name} page should have at least one <${selector}>`).toBeGreaterThan(0);
    }

    // Verify NO console errors
    expect(errors, `${name} page should have 0 console errors, got: ${errors.join('; ')}`).toEqual([]);
  });

  test(`${name} page has no broken images`, async ({ page }) => {
    await page.goto(route, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(1000);

    const images = await page.locator('img').all();
    for (const img of images) {
      const naturalWidth = await img.evaluate((el: HTMLImageElement) => el.naturalWidth);
      // naturalWidth === 0 means the image failed to load
      expect(naturalWidth, `Broken image on ${name} page`).toBeGreaterThan(0);
    }
  });
}

test('FireAlarm: clicking detector selects it, does NOT add new one', async ({ page }) => {
  // V191 regression test: clicking a detector should select it, not add a new one
  await page.goto('/fire-alarm', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(1500);

  // Count initial detectors
  const initialCount = await page.locator('svg g[transform]').count();

  // Click on empty canvas to add a detector
  const canvas = page.locator('.bg-slate-900.border.border-slate-700');
  await canvas.click({ position: { x: 300, y: 200 } });
  await page.waitForTimeout(500);

  const afterAddCount = await page.locator('svg g[transform]').count();
  expect(afterAddCount, 'Clicking empty canvas should add exactly 1 detector').toBe(initialCount + 1);

  // Now click ON the detector — should NOT add a new one
  const firstDetector = page.locator('svg g[transform]').first();
  const box = await firstDetector.boundingBox();
  expect(box, 'Detector should have a bounding box').not.toBeNull();

  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.waitForTimeout(500);

  const afterClickCount = await page.locator('svg g[transform]').count();
  expect(afterClickCount, 'Clicking on a detector should NOT add a new one').toBe(afterAddCount);
});

test('Connections: create connection modal opens with form fields', async ({ page }) => {
  await page.goto('/connections', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(1000);

  // Click "Create Connection" button
  await page.getByRole('button', { name: /create connection/i }).click();
  await page.waitForTimeout(500);

  // Verify modal is open with form fields
  await expect(page.locator('text=Source Element')).toBeVisible({ timeout: 3000 });
  await expect(page.locator('text=Target Element')).toBeVisible();
  await expect(page.locator('text=Relationship Type')).toBeVisible();
});

test('Dashboard: no React key warnings', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && msg.text().includes('key')) {
      errors.push(msg.text());
    }
  });

  await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(1500);

  expect(errors, 'Dashboard should not have React key warnings').toEqual([]);
});
