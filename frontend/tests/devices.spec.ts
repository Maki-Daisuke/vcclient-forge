import { openControlSections } from './catalog-fixtures';
import { test, expect, type Page } from '@playwright/test';
import { configuration, inputDevices, outputDevices, mockCatalog } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

const microphone = (page: Page) => page.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true });

test.beforeEach(async ({ page }) => { await mockCatalog(page); });

test('rescans once while stopped and requires reselection if an index changes identity', async ({ page }) => {
  const state = await mockSession(page);
  const requests: string[] = [];
  await page.route('**/api/audio-device-manager/input_devices**', route => {
    const query = new URL(route.request().url()).search;
    requests.push(`input${query}`);
    return route.fulfill({ json: query ? [
      { index: 8, name: 'Different microphone', host_api: 'Windows WASAPI' },
      { index: 32, name: 'USB microphone', host_api: 'Windows WASAPI' },
    ] : inputDevices });
  });
  await page.route('**/api/audio-device-manager/output_devices**', route => {
    requests.push(`output${new URL(route.request().url()).search}`);
    return route.fulfill({ json: outputDevices });
  });
  await page.goto('/');
  await openControlSections(page);
  requests.length = 0;
  await page.getByRole('button', { name: 'デバイス再検出' }).click();
  await expect(microphone(page).locator('option:checked')).toHaveText('未選択');
  expect(requests).toEqual(['input?reload=true', 'output']);
  expect(state.config.audio_input_device_index).toBe(8);
  const start = page.getByRole('button', { name: '開始', exact: true });
  await expect(start).toHaveAttribute('aria-disabled', 'true');
  await microphone(page).selectOption('32');
  await expect.poll(() => state.config.audio_input_device_index).toBe(32);
  await expect(start).toHaveAttribute('aria-disabled', 'false');
  expect(state.config.audio_input_device_sample_rate).toBe(-1);
});

test('does not reinitialize audio while it is running', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('reload=true')) requests.push(request.url()); });
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('button', { name: 'デバイス再検出' })).toBeDisabled();
  expect(requests).toHaveLength(0);
});

test('preserves the selection when device identities do not change', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const reloaded = page.waitForResponse(response => response.url().includes('input_devices?reload=true'));
  await page.getByRole('button', { name: 'デバイス再検出' }).click();
  await reloaded;
  await expect(page.getByRole('button', { name: 'デバイス再検出' })).toBeEnabled();
  await expect(microphone(page).locator('option:checked')).toHaveText('USB microphone (Windows WASAPI)');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveAttribute('aria-disabled', 'false');
  expect(state.writes).toHaveLength(0);
});

test('does not trust the old device list after a failed rescan', async ({ page }) => {
  const state = await mockSession(page);
  await page.route('**/api/audio-device-manager/input_devices**', route => {
    return new URL(route.request().url()).search ? route.fulfill({ status: 503 }) : route.fulfill({ json: inputDevices });
  });
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('button', { name: 'デバイス再検出' }).click();
  await expect(page.getByRole('alert')).toContainText('デバイスを再検出できませんでした');
  await expect(microphone(page)).toBeDisabled();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveAttribute('aria-disabled', 'true');
  expect(state.config.audio_input_device_index).toBe(8);
});

test('allows explicitly choosing a new device that reused the old index', async ({ page }) => {
  const state = await mockSession(page);
  await page.route('**/api/audio-device-manager/input_devices**', route => {
    return route.fulfill({ json: new URL(route.request().url()).search
      ? [{ index: 8, name: 'Replacement microphone', host_api: 'Windows WASAPI' }] : inputDevices });
  });
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('button', { name: 'デバイス再検出' }).click();
  await expect(microphone(page).locator('option:checked')).toHaveText('未選択');
  await microphone(page).selectOption('8');
  await expect.poll(() => state.writes.length).toBeGreaterThan(0);
  await expect(microphone(page).locator('option:checked')).toHaveText('Replacement microphone (Windows WASAPI)');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveAttribute('aria-disabled', 'false');
});

test('allows choosing no monitor after its device identity changes', async ({ page }) => {
  const state = await mockSession(page);
  state.config.audio_monitor_device_index = 25;
  await page.route('**/api/audio-device-manager/output_devices**', route => route.fulfill({ json: [
    outputDevices[1], { index: 25, name: 'Replacement output', host_api: 'Windows WASAPI' },
  ] }));
  await page.goto('/');
  await openControlSections(page);
  await page.route('**/api/audio-device-manager/output_devices**', route => route.fulfill({ json: [
    outputDevices[1], { index: 25, name: 'Another output', host_api: 'Windows WASAPI' },
  ] }));
  await page.getByRole('button', { name: 'デバイス再検出' }).click();
  const monitor = page.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true });
  await expect(monitor.locator('option:checked')).toHaveText('未選択');
  await monitor.selectOption('-1');
  await expect.poll(() => state.config.audio_monitor_device_index).toBe(-1);
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveAttribute('aria-disabled', 'false');
});

test('filters Windows devices until legacy devices are enabled', async ({ page }) => {
  await page.route('**/api/audio-device-manager/output_devices', route => route.fulfill({ json: [
    ...outputDevices, { index: 33, name: 'Legacy speaker', host_api: 'MME' },
  ] }));
  await page.goto('/');
  await openControlSections(page);
  const toggle = page.getByRole('checkbox', { name: 'レガシーデバイスを表示' });
  await expect(toggle).not.toBeChecked();
  await expect(microphone(page).getByRole('option', { name: /Other microphone/ })).toHaveCount(0);
  const output = page.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true });
  const monitor = page.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true });
  await expect(output.getByRole('option', { name: /Legacy speaker/ })).toHaveCount(0);
  await expect(monitor.getByRole('option', { name: /Legacy speaker/ })).toHaveCount(0);
  await toggle.check();
  await expect(microphone(page).getByRole('option', { name: /Other microphone/ })).toBeEnabled();
  await expect(output.getByRole('option', { name: /Legacy speaker/ })).toBeEnabled();
  await expect(monitor.getByRole('option', { name: /Legacy speaker/ })).toBeEnabled();
  await toggle.uncheck();
  await expect(output.getByRole('option', { name: /Legacy speaker/ })).toHaveCount(0);
});

test('retains a selected legacy device without offering it as a selectable option', async ({ page }) => {
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({
    json: { ...configuration, audio_input_device_index: 11 },
  }));
  await page.goto('/');
  await openControlSections(page);
  const selected = microphone(page).locator('option:checked');
  await expect(selected).toHaveText('Other microphone (MME)');
  await expect(selected).toHaveAttribute('disabled', '');
  await page.getByRole('checkbox', { name: 'レガシーデバイスを表示' }).check();
  await expect(selected).not.toHaveAttribute('disabled');
});

test('keeps all devices visible on a non-Windows backend', async ({ page }) => {
  await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({ json: [
    { index: 8, name: 'CoreAudio microphone', host_api: 'Core Audio' },
    { index: 11, name: 'Other microphone', host_api: 'Core Audio' },
  ] }));
  await page.route('**/api/audio-device-manager/output_devices', route => route.fulfill({ json: [
    { index: 11, name: 'CoreAudio speakers', host_api: 'Core Audio' },
  ] }));
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('checkbox', { name: 'レガシーデバイスを表示' })).toHaveCount(0);
  await expect(microphone(page).getByRole('option', { name: /Other microphone/ })).toHaveCount(1);
});

test('offers legacy devices when Windows has no WASAPI devices', async ({ page }) => {
  await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({ json: [inputDevices[0]] }));
  await page.route('**/api/audio-device-manager/output_devices', route => route.fulfill({ json: [] }));
  await page.goto('/');
  await openControlSections(page);
  const toggle = page.getByRole('checkbox', { name: 'レガシーデバイスを表示' });
  await expect(toggle).toBeVisible();
  await expect(microphone(page).getByRole('option', { name: /Other microphone/ })).toHaveCount(0);
  await toggle.check();
  await expect(microphone(page).getByRole('option', { name: /Other microphone/ })).toHaveCount(1);
});

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
  await openControlSections(page);
  await expect(microphone(page).locator('option:checked')).toHaveText('USB microphone (Windows WASAPI)');
  const dialog = page;
  await expect(dialog.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true }).locator('option:checked')).toHaveText('USB microphone (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true }).locator('option:checked')).toHaveText('USB speakers (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true }).locator('option:checked')).toHaveText('Monitor headphones (Windows WASAPI)');
  for (const field of await dialog.locator('.device-row select').all()) {
    if (await field.getAttribute('aria-label')) await expect(field).toBeDisabled();
    else await expect(field).toBeEnabled();
  }
  expect(requests.length).toBeGreaterThanOrEqual(5);
  expect(requests.every(query => query === '')).toBe(true);
});

test('missing and empty device lists retain configured IDs instead of selecting another device', async ({ page }) => {
  await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({ json: [inputDevices[0]] }));
  await page.route('**/api/audio-device-manager/output_devices', route => route.fulfill({ json: [] }));
  await page.goto('/');
  await openControlSections(page);
  await expect(microphone(page).locator('option:checked')).toHaveText('デバイス #8（一覧にありません）');
  const dialog = page;
  await expect(dialog.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true }).locator('option:checked')).toHaveText('デバイス #11（一覧にありません）');
  await expect(dialog.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true }).locator('option:checked')).toHaveText('未選択');
});

test('failed device refresh clears old names without clearing settings, and retry updates names', async ({ page }) => {
  await page.goto('/');
  await openControlSections(page);
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
  await expect(microphone(page).locator('option:checked')).toHaveText('Renamed microphone (MME)');
});

test('slow device lists do not block settings, time out, and recover on reload', async ({ page }) => {
  await page.clock.install();
  await page.route('**/api/audio-device-manager/input_devices', () => {});
  await page.goto('/');
  await openControlSections(page);
  await expect(microphone(page)).toContainText('デバイス #8（一覧を読み込み中');
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await page.clock.fastForward(8_001);
  await expect(microphone(page)).toContainText('一覧を取得できません');
  await page.unroute('**/api/audio-device-manager/input_devices');
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(microphone(page).locator('option:checked')).toHaveText('USB microphone (Windows WASAPI)');
});

for (const invalid of [
  { name: 'invalid types', data: [{ index: '8', name: 123, host_api: 'MME' }] },
  { name: 'duplicate IDs', data: [inputDevices[1], inputDevices[1]] },
]) {
  test(`rejects device ${invalid.name} without losing configuration`, async ({ page }) => {
    await page.route('**/api/audio-device-manager/input_devices', route => route.fulfill({ json: invalid.data }));
    await page.goto('/');
  await openControlSections(page);
    await expect(microphone(page)).toContainText('一覧を取得できません');
    await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  });
}
