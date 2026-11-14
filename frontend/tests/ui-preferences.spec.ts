import { test, expect } from './test-fixtures';
import { mockCatalog } from './catalog-fixtures';

test.use({ storageState: { cookies: [], origins: [] } });
test.beforeEach(async ({ page }) => { await mockCatalog(page); });

test('defaults to English and remembers language and theme', async ({ page }) => {
  await page.goto('/');
  const language = page.locator('.header-actions select');
  await expect(language).toHaveValue('en');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await language.selectOption('ja');
  await page.getByRole('button', { name: '配色を切り替える' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(language).toHaveValue('ja');
  await expect(page.locator('html')).toHaveAttribute('lang', 'ja');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await language.selectOption('en');
  await page.getByRole('button', { name: 'Toggle color theme' }).click();
  await page.reload();
  await expect(language).toHaveValue('en');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('uses safe defaults for invalid stored preferences', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vcclient-forge.ui-preferences.v1', '{"language":"invalid","theme":"invalid"}'));
  await page.goto('/');
  await expect(page.locator('.header-actions select')).toHaveValue('en');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('keeps controls usable when storage is unavailable', async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage unavailable'); } }); });
  await page.goto('/');
  await page.locator('.header-actions select').selectOption('ja');
  await page.getByRole('button', { name: '配色を切り替える' }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'ja');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});
