import { test, expect, type Page } from '@playwright/test';

test.describe('Complete Button Audit for BazSpark UI', () => {
  const pages = [
    { path: '/', name: 'Home-Landing' },
    { path: '/dashboard', name: 'Dashboard' },
    { path: '/projects', name: 'Projects' },
    { path: '/autocad', name: 'AutoCAD' },
    { path: '/autocad/draw', name: 'AutoCAD-Draw' },
    { path: '/revit', name: 'Revit' },
    { path: '/revit/create', name: 'Revit-Create' },
    { path: '/digital-twin', name: 'Digital-Twin' },
    { path: '/digital-twin/config', name: 'Digital-Twin-Config' },
    { path: '/elements', name: 'Elements' },
    { path: '/connections', name: 'Connections' },
    { path: '/conflicts', name: 'Conflicts' },
    { path: '/reports', name: 'Reports' },
    { path: '/settings', name: 'Settings' },
    { path: '/settings/cad', name: 'Settings-CAD' },
  ];

  for (const pageInfo of pages) {
    test(`should capture screenshot and detect buttons on ${pageInfo.name}`, async ({ page }) => {
      await page.goto(pageInfo.path);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      await page.screenshot({ path: `test-results/screenshot-${pageInfo.name}.png`, fullPage: true });

      const buttons = await page.locator('button, a[role="button"], input[type="submit"], input[type="button"]').all();
      const buttonTexts: string[] = [];
      for (const btn of buttons) {
        const text = await btn.textContent();
        if (text && text.trim()) {
          buttonTexts.push(text.trim());
        }
      }

      console.log(`${pageInfo.name} buttons: ${buttonTexts.join(', ') || 'None detected'}`);
      const hasButtons = buttonTexts.length > 0;
      expect(hasButtons || pageInfo.name === 'Home-Landing').toBe(true);
    });
  }
});

</parameter>
<parameter name="task_progress">- [x] Explore project structure
- [x] Understand project purpose and contents
- [x] Determine task requirements (debug test failures)
- [x] Read and analyze test files
- [x] Run tests to identify failures
- [x] Fix identified issues (install Puppeteer deps + Chrome)
- [x] Fix identified issues (use system Chrome in test)
- [x] Verify fixes by running tests
- [x] Check frontend tests for failures
- [x] Confirm no frontend test code defects
- [x] Review existing Playwright test setup
- [x] Install frontend dependencies
- [x] Install Playwright browsers
- [x] Create comprehensive Playwright button audit with screenshots
- [ ] Fix corrupted Playwright test file completely
- [ ] Run Playwright tests with screenshots
- [ ] Review screenshots and UI state
- [ ] Provide professional UI assessment
- [ ] Report issues and recommendations</parameter>
</write_to_file>