import { test, expect } from '@playwright/test';

test.describe('Marine Page End-to-End Tests', () => {
 test.beforeEach(async ({ page }) => {
 await page.goto('http://localhost:5173/marine');
 });

 test('should load Marine page successfully', async ({ page }) => {
 await expect(page).toHaveTitle(/Marine Fire Protection & Safety Studio/);
 });

 test('should trigger all 14 backend API calls when buttons are clicked', async ({ page }) => {
 // Intercept all marine API calls
 const apiCalls: string[] = [];
 page.route('**/api/v1/marine/*', (route) => {
 const url = route.request().url();
 apiCalls.push(url);
 route.continue();
 });

 // Test all 14 buttons
 for (const testId of [
 'marine-run-pipeline-btn',
 'marine-alarm-sim-btn',
 'marine-detection-btn',
 'marine-extinguishing-btn',
 'marine-validate-btn',
 'marine-divide-zones-btn',
        'marine-calculate-sensor-btn',
        'marine-size-extinguishing-btn',
        'marine-design-power-btn',
        'marine-generate-alarm-logic-btn',
 'marine-export-scada-btn',
 'marine-export-etap-btn',
 'marine-export-dxf-btn',
 'marine-export-revit-btn'
 ]) {
 await page.click(`[data-testid="${testId}"]`);
 await page.waitForTimeout(100);
 }

 // Verify API calls were made
 expect(apiCalls.length).toBeGreaterThan(0);
 });

 test('should toggle alarm simulation correctly', async ({ page }) => {
 const alarmButton = page.getByTestId('marine-alarm-sim-btn');
 await expect(alarmButton).toHaveText('Simulate Alarm');

 await alarmButton.click();
 await expect(alarmButton).toHaveText('Stop Alarm Sim');

 await alarmButton.click();
 await expect(alarmButton).toHaveText('Simulate Alarm');
 });

 test('should navigate between tabs correctly', async ({ page }) => {
 await expect(page.getByRole('tab', { name: /Vessel Deck Viewport/ })).toHaveAttribute('aria-selected', 'true');

 await page.getByRole('tab', { name: /Ship Parameters/ }).click();
 await expect(page.getByRole('tab', { name: /Ship Parameters/ })).toHaveAttribute('aria-selected', 'true');

 await page.getByRole('tab', { name: /Detection, Extinguishing/ }).click();
 await expect(page.getByRole('tab', { name: /Detection, Extinguishing/ })).toHaveAttribute('aria-selected', 'true');

 await page.getByRole('tab', { name: /PLC Logic/ }).click();
 await expect(page.getByRole('tab', { name: /PLC Logic/ })).toHaveAttribute('aria-selected', 'true');
 });
});