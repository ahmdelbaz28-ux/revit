import { test, expect } from '@playwright/test';
import { installApiMock } from './helpers/authMock';

test('can toggle dark mode via TopBar button', async ({ page }) => {
  // Pre-authenticate so the app loads without redirecting to /login
  await page.unroute('**/api/**');
  await installApiMock(page, { preAuthenticated: true });

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');

  // The dark mode toggle is directly in the TopBar header (no dropdown needed)
  const toggleBtn = page.locator('button[aria-label="Toggle dark mode"]');
  await expect(toggleBtn).toBeVisible({ timeout: 10000 });

  // Toggle dark mode ON
  await toggleBtn.click();
  await expect(page.locator('html')).toHaveClass(/dark/);

  // Toggle dark mode OFF
  await toggleBtn.click();
  await expect(page.locator('html')).not.toHaveClass(/dark/);
});
