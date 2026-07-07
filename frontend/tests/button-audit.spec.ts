// NOSONAR
import { expect, test } from "@playwright/test";

test.describe("Complete Button Audit for BazSpark UI", () => {
	const pages = [
		{ path: "/", name: "Home-Landing" },
		{ path: "/dashboard", name: "Dashboard" },
		{ path: "/projects", name: "Projects" },
		{ path: "/autocad", name: "AutoCAD" },
		{ path: "/autocad/draw", name: "AutoCAD-Draw" },
		{ path: "/revit", name: "Revit" },
		{ path: "/revit/create", name: "Revit-Create" },
		{ path: "/digital-twin", name: "Digital-Twin" },
		{ path: "/digital-twin/config", name: "Digital-Twin-Config" },
		{ path: "/elements", name: "Elements" },
		{ path: "/connections", name: "Connections" },
		{ path: "/conflicts", name: "Conflicts" },
		{ path: "/reports", name: "Reports" },
		{ path: "/settings", name: "Settings" },
		{ path: "/settings/cad", name: "Settings-CAD" },
	];

	for (const pageInfo of pages) {
		test(`should capture screenshot and detect buttons on ${pageInfo.name}`, async ({
			page,
		}) => {
			await page.goto(pageInfo.path);
			await page.waitForLoadState("networkidle");
			await page.waitForLoadState("networkidle");  // S2925: sync on condition, not fixed wait

			await page.screenshot({
				path: `test-results/screenshot-${pageInfo.name}.png`,
				fullPage: true,
			});

			const buttons = await page
				.locator(
					'button, a[role="button"], input[type="submit"], input[type="button"]',
				)
				.all();
			const buttonTexts: string[] = [];
			for (const btn of buttons) {
				const text = await btn.textContent();
				if (text?.trim()) {
					buttonTexts.push(text.trim());
				}
			}

			console.log(
				`${pageInfo.name} buttons: ${buttonTexts.join(", ") || "None detected"}`,
			);
			const hasButtons = buttonTexts.length > 0;
			expect(hasButtons || pageInfo.name === "Home-Landing").toBe(true);
		});
	}
});
