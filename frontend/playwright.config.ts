import { defineConfig, devices } from '@playwright/test';

const port = process.env.PLAYWRIGHT_PORT || '5174';
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  use: {
    baseURL,
    ...devices['Desktop Chrome'],
    storageState: { cookies: [], origins: [{ origin: baseURL, localStorage: [{ name: 'vcclient-forge.ui-preferences.v1', value: '{"language":"ja","theme":"light"}' }] }] },
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `npm run build && npm run preview -- --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
  },
});
