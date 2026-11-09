import { test, expect } from '@playwright/test';
import { mockCatalog, openControlSections } from './catalog-fixtures';

test.beforeEach(async ({ page }) => { await mockCatalog(page); });

test('places voice controls with the selected model and groups other controls in four accordions', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('main > .configuration-status')).toBeHidden();
  const groups = page.locator('.controls-column > details.control-group');
  await expect(groups.locator('summary')).toHaveText(['オーディオデバイス', '音量コントロール', 'ノイズ抑制', '推論設定']);
  await expect(page.locator('.transport-row button')).toHaveText(['開始', 'パススルー', '録音']);
  await expect(page.locator('.monitor-column .transport-row')).toBeVisible();
  await expect(page.getByRole('button', { name: '設定', exact: true })).toHaveCount(0);
  await openControlSections(page);
  await expect(page.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true })).toHaveCount(1);
  const mode = page.getByRole('group', { name: '入出力モード' });
  await expect(page.getByRole('heading', { name: '入出力モード' })).toHaveCount(0);
  await expect(mode.getByRole('radio', { name: 'サーバーモード' })).toBeChecked();
  await expect(mode.getByRole('radio', { name: 'クライアントモード' })).toBeDisabled();
  await expect(groups.nth(0).getByRole('slider', { name: 'ノイズゲートのしきい値' })).toHaveCount(0);
  await expect(groups.nth(2).getByRole('slider', { name: 'ノイズゲートのしきい値' })).toBeVisible();
  await expect(groups.nth(2).getByRole('heading', { name: 'クライアントモード専用' })).toBeVisible();
  await expect(groups.nth(1).getByRole('slider')).toHaveCount(2);
  await expect(groups.nth(3).getByRole('combobox', { name: '優先デバイス' })).toBeVisible();
  await expect(page.locator('.models-panel .voice-settings').getByRole('radio', { name: 'RMVPE' })).toBeDisabled();
  await expect(page.locator('.models-panel .voice-settings').getByRole('slider', { name: 'ピッチ調整' })).toBeVisible();
  for (const name of ['ピッチ調整', 'Index使用率', 'ピッチ推定器']) {
    await expect(page.locator('.voice-settings').getByRole('heading', { name, exact: true })).toBeVisible();
  }
  await expect(page.locator('.voice-settings').getByRole('heading', { name: 'ボイスコントロール' })).toHaveCount(0);
  await groups.nth(0).locator('summary').click();
  await expect(groups.nth(0)).not.toHaveAttribute('open');
  await expect(groups.nth(0).getByRole('combobox', { name: '入力デバイス（マイク）' })).toHaveCount(0);
  await expect(groups.nth(1).getByRole('slider', { name: '入力音量' })).toBeVisible();
  await groups.nth(0).locator('summary').click();
  await expect(groups.nth(0).getByRole('combobox', { name: '入力デバイス（マイク）' })).toBeVisible();
  await groups.nth(2).locator('summary').click();
  await expect(groups.nth(2)).not.toHaveAttribute('open');
  await expect(groups.nth(2).getByRole('slider', { name: 'ノイズゲートのしきい値' })).toHaveCount(0);
  await expect(groups.nth(0).getByRole('combobox', { name: '入力デバイス（マイク）' })).toBeVisible();
  await groups.nth(2).locator('summary').click();
});

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
  await openControlSections(page);
  await expect(page.getByRole('heading', { name: 'VCClient Forge' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveCount(0);
  for (const name of ['パススルー', '録音']) {
    await expect(page.getByRole('button', { name, exact: true })).toBeDisabled();
  }
  const sliders = page.getByRole('slider');
  await expect(sliders).toHaveCount(10);
  for (const name of ['入力音量', '出力音量']) await expect(page.getByRole('slider', { name, exact: true })).toBeEnabled();
  for (const name of ['ピッチ調整', 'Index使用率']) await expect(page.getByRole('slider', { name, exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '配色を切り替える' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  expect([...new Set(backendRequests.map(url => new URL(url).pathname))].sort()).toEqual([
    '/api/audio-device-manager/input_devices', '/api/audio-device-manager/output_devices',
    '/api/configuration-manager/configuration', '/api/gpu-device-manager/devices',
    '/api/local-voice-changer-interface/information', '/api/slot-manager/slots',
  ]);
  expect(errors).toEqual([]);
});

test('starts closed and restores each section after reloading', async ({ page }) => {
  await page.goto('/');
  const groups = page.locator('.controls-column > details.control-group');
  for (const group of await groups.all()) await expect(group).not.toHaveAttribute('open');
  await groups.nth(0).locator('summary').click();
  await groups.nth(1).locator('summary').click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('vcclient-forge.control-sections.v1')))
    .toContain('"volume":true');
  await page.reload();
  await expect(groups.nth(0)).toHaveAttribute('open');
  await expect(groups.nth(1)).toHaveAttribute('open');
  await expect(groups.nth(2)).not.toHaveAttribute('open');
  await expect(groups.nth(3)).not.toHaveAttribute('open');
  await groups.nth(0).locator('summary').click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('vcclient-forge.control-sections.v1')))
    .toContain('"input":false');
  await page.reload();
  await expect(groups.nth(0)).not.toHaveAttribute('open');
  await expect(groups.nth(1)).toHaveAttribute('open');
});

test('invalid or unavailable storage leaves controls usable and initially closed', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('vcclient-forge.control-sections.v1', '{invalid'));
  await page.goto('/');
  const groups = page.locator('.controls-column > details.control-group');
  for (const group of await groups.all()) await expect(group).not.toHaveAttribute('open');
  await groups.nth(0).locator('summary').click();
  await expect(groups.nth(0)).toHaveAttribute('open');
});

test('controls remain usable when storage access throws', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new Error('Storage unavailable'); } });
  });
  await page.goto('/');
  const groups = page.locator('.controls-column > details.control-group');
  for (const group of await groups.all()) await expect(group).not.toHaveAttribute('open');
  await groups.nth(0).locator('summary').click();
  await expect(groups.nth(0)).toHaveAttribute('open');
});

test('dialogs open, trap focus, close with Escape, and restore focus', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  for (const name of ['アップロード', '編集', '詳細設定', 'キー設定', 'ログ', 'このアプリについて']) {
    const trigger = page.getByRole('button', { name, exact: true });
    await trigger.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    for (const field of await dialog.locator('input, select, textarea').all()) {
      if (name === 'アップロード' || name === '編集') await expect(field).toBeEnabled();
      else await expect(field).toBeDisabled();
    }
    await page.keyboard.press('Tab');
    await expect(dialog).not.toContainText('表示はサンプルです。設定の変更や音声の操作は、まだ利用できません。');
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
  }
});

test('nested model dialogs restore their parent', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'モデルを削除', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'このモデルを削除しますか？' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'このモデルを削除しますか？' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'モデルを削除', exact: true })).toBeVisible();
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

test('places transport before monitoring on a narrow screen', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/');
  await expect(page.locator('.models-panel .voice-settings')).toBeVisible();
  const transport = await page.locator('.transport-row').boundingBox();
  const monitoring = await page.locator('.monitor-column .performance').boundingBox();
  expect(transport).not.toBeNull();
  expect(monitoring).not.toBeNull();
  expect(transport!.y).toBeLessThan(monitoring!.y);
});

for (const width of [1280, 375]) {
  test(`keeps English audio buttons on one row at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 812 });
    await page.goto('/');
    await page.locator('.header-actions select').selectOption('en');
    const buttons = page.locator('.transport-row button');
    await expect(buttons).toHaveText(['Start', 'Passthrough', 'Record']);
    const positions = await buttons.evaluateAll(elements => elements.map(element => element.getBoundingClientRect().top));
    expect(Math.max(...positions) - Math.min(...positions)).toBeLessThanOrEqual(1);
  });
}
