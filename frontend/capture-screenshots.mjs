/**
 * Screenshot capture script for FireAI Electron app.
 * Usage: xvfb-run node capture-screenshots.mjs
 */
import { app, BrowserWindow } from 'electron';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '..', 'docs', 'assets', 'screenshots');
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

const PAGES = {
  'dashboard': '/',
  'engineering-workspace': '/engineering',
  'fire-alarm-designer': '/fire-alarm',
  'compliance-center': '/reports',
  'project-management': '/projects',
  'connections': '/connections',
  'elements': '/elements',
};

async function capture() {
  fs.mkdirSync(OUT, { recursive: true });

  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    show: false,
  });

  for (const [name, route] of Object.entries(PAGES)) {
    try {
      const url = `${BACKEND_URL}${route}`;
      console.log(`Navigating to ${url}...`);
      await win.loadURL(url);
      await new Promise(r => setTimeout(r, 3000));
      const image = await win.webContents.capturePage();
      const p = path.join(OUT, `${name}.png`);
      fs.writeFileSync(p, image.toPNG());
      console.log(`  Saved ${p} (${image.getSize().width}x${image.getSize().height})`);
    } catch (e) {
      console.error(`  FAILED ${name}: ${e.message}`);
    }
  }

  win.close();
  app.quit();
}

app.whenReady().then(capture);
