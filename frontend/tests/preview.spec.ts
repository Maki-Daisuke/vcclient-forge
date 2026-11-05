import { test, expect } from '@playwright/test';
import { mockCatalog } from './catalog-fixtures';

test.beforeEach(async ({ page }) => { await mockCatalog(page); });

test('initialization only reads backend data and keeps browser audio and device access disabled', async ({ page }) => {
  const errors: string[] = [];
  const backendRequests: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/\/api\/|socket\.io|\/ws\//.test(request.url())) backendRequests.push(request.url());
  });
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = () => { throw new Error('Unexpected microphone access'); };
    navigator.mediaDevices.enumerateDevices = () => { throw new Error('Unexpected device enumeration'); };
    window.WebSocket = class { constructor() { throw new Error('Unexpected WebSocket'); } } as unknown as typeof WebSocket;
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'VCClient Forge' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  for (const name of ['開始', '停止', 'パススルー', '録音']) {
    await expect(page.getByRole('button', { name, exact: true })).toBeDisabled();
  }
  const sliders = page.getByRole('slider');
  await expect(sliders).toHaveCount(6);
  for (const slider of await sliders.all()) await expect(slider).toBeDisabled();
  await page.getByRole('button', { name: '配色を切り替える' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  expect(backendRequests.map(url => new URL(url).pathname).sort()).toEqual([
    '/api/audio-device-manager/input_devices', '/api/audio-device-manager/output_devices',
    '/api/configuration-manager/configuration', '/api/slot-manager/slots',
  ]);
  expect(errors).toEqual([]);
});

test('dialogs open, trap focus, close with Escape, and restore focus', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  for (const name of ['設定', 'モデル管理', 'アップロード', '編集', '詳細設定', 'キー設定', 'ログ', 'このアプリについて']) {
    const trigger = page.getByRole('button', { name, exact: true });
    await trigger.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    for (const field of await dialog.locator('input, select, textarea').all()) await expect(field).toBeDisabled();
    await page.keyboard.press('Tab');
    await expect(dialog.locator('.preview-notice')).toContainText(/サンプル|読み取り専用/);
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  }
});

test('nested model dialogs restore their parent', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'モデル管理', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'サンプルモデル', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'サンプルモデル一覧' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'モデル管理' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('all community languages and narrow RTL layouts render without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/');
  for (const language of ['en', 'ja', 'ko', 'de', 'ar', 'el', 'es', 'fr', 'it', 'la', 'ms', 'ru', 'zh']) {
    await page.locator('.header-actions select').selectOption(language);
    await expect(page.locator('html')).toHaveAttribute('lang', language);
    await expect(page.locator('html')).toHaveAttribute('dir', language === 'ar' ? 'rtl' : 'ltr');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.locator('main')).not.toContainText(/common\.|forge\./);
  }
});
