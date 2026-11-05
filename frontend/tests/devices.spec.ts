import { test, expect, type Page } from '@playwright/test';
import { configuration, inputDevices, mockCatalog } from './catalog-fixtures';

const microphone = (page: Page) => page.locator('.input-section select');

test.beforeEach(async ({ page }) => { await mockCatalog(page); });

test('matches sparse IDs and uses output devices for the monitor without requesting a rescan', async ({ page }) => {
  const requests: string[] = [];
  page.on('request', request => {
    if (request.url().includes('/api/')) {
      expect(request.method()).toBe('GET');
      requests.push(new URL(request.url()).search);
    }
  });
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({
    json: { ...configuration, audio_monitor_device_index: 25 },
  }));
  await page.goto('/');
  await expect(microphone(page)).toHaveText('USB microphone (Windows WASAPI)');
  await page.getByRole('button', { name: '設定', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true })).toHaveText('USB microphone (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true })).toHaveText('USB speakers (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true })).toHaveText('Monitor headphones (Windows WASAPI)');
  for (const field of await dialog.getByRole('combobox').all()) await expect(field).toBeDisabled();
  expect(requests).toEqual(['', '', '', '']);
});

test('missing and empty device lists retain configured IDs instead of selecting another device', async ({ page }) => {
  await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({ json: [inputDevices[0]] }));
  await page.route('**/api/audio-device-manager/output_devices', route => route.fulfill({ json: [] }));
  await page.goto('/');
  await expect(microphone(page)).toHaveText('デバイス #8（一覧にありません）');
  await page.getByRole('button', { name: '設定', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true })).toHaveText('デバイス #11（一覧にありません）');
  await expect(dialog.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true })).toHaveText('未選択');
});

test('failed device refresh clears old names without clearing settings, and retry updates names', async ({ page }) => {
  await page.goto('/');
  await expect(microphone(page)).toContainText('USB microphone');
  await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({ status: 503 }));
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(microphone(page)).toContainText('デバイス #8（一覧を取得できません');
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({
    json: [{ index: 8, name: 'Renamed microphone', host_api: 'MME' }],
  }));
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(microphone(page)).toHaveText('Renamed microphone (MME)');
});

test('slow device lists do not block settings, time out, and recover on reload', async ({ page }) => {
  await page.clock.install();
  await page.route('**/api/audio-device-manager/input_devices', () => {});
  await page.goto('/');
  await expect(microphone(page)).toContainText('デバイス #8（一覧を読み込み中');
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await page.clock.fastForward(8_001);
  await expect(microphone(page)).toContainText('一覧を取得できません');
  await page.unroute('**/api/audio-device-manager/input_devices');
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(microphone(page)).toHaveText('USB microphone (Windows WASAPI)');
});

for (const invalid of [
  { name: 'invalid types', data: [{ index: '8', name: 123, host_api: 'MME' }] },
  { name: 'duplicate IDs', data: [inputDevices[1], inputDevices[1]] },
]) {
  test(`rejects device ${invalid.name} without losing configuration`, async ({ page }) => {
    await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({ json: invalid.data }));
    await page.goto('/');
    await expect(microphone(page)).toContainText('一覧を取得できません');
    await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  });
}
