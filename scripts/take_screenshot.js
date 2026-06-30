const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });
  
  // Dashboard page
  console.log('Taking dashboard screenshot...');
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));
  await page.screenshot({ path: 'docs/assets/screenshot_dashboard.png', fullPage: true });
  console.log('Dashboard screenshot saved');
  
  // Fire Alarm page
  console.log('Taking fire alarm screenshot...');
  await page.goto('http://localhost:5173/fire-alarm', { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));
  await page.screenshot({ path: 'docs/assets/screenshot_firealarm.png', fullPage: true });
  console.log('Fire alarm screenshot saved');
  
  // Reports page
  console.log('Taking reports screenshot...');
  await page.goto('http://localhost:5173/reports', { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));
  await page.screenshot({ path: 'docs/assets/screenshot_reports.png', fullPage: true });
  console.log('Reports screenshot saved');
  
  await browser.close();
  console.log('All screenshots taken successfully!');
})();