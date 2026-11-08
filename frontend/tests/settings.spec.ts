import { openControlSections } from './catalog-fixtures';
import { test, expect, type Page } from '@playwright/test';
import { configuration, fulfillCatalog, mockCatalog, slots } from './catalog-fixtures';

async function openSettings(page: Page) {
  return page;
}

for (const { value, fraction } of [
  { value: 0.05, fraction: 0 },
  { value: 0.5, fraction: 0.5 },
  { value: 5, fraction: 1 },
  { value: 7, fraction: 1 },
]) {
  test(`displays chunk duration ${value} s on the logarithmic slider`, async ({ page }) => {
    await mockCatalog(page);
    await page.route('**/api/slot-manager/slots', route => fulfillCatalog(route, slots.map(slot => slot.slot_index === 7 ? { ...slot, chunk_sec: value } : slot)));
    await page.goto('/');
    await openControlSections(page);
    const slider = page.getByRole('slider', { name: 'チャンクフレーム（秒）', exact: true });
    await expect(slider).toBeEnabled();
    await expect(slider).toHaveAttribute('aria-valuetext', `${value} s`);
    const field = page.locator('.log-slider').filter({ has: slider });
    const track = await field.locator('.slider-track').boundingBox();
    const thumb = await slider.boundingBox();
    expect(track).not.toBeNull();
    expect(thumb).not.toBeNull();
    const position = (thumb!.x + thumb!.width / 2 - track!.x) / track!.width;
    expect(Math.abs(position - fraction)).toBeLessThan(0.04);
    if (value > 5) await expect(field).toContainText('表示範囲外');
  });
}

for (const testCase of [
  { label: 'Extraフレーム（秒）', key: 'extra_frame_sec', value: Math.sqrt(0.01 * 10), fraction: 0.5 },
  { label: 'クロスフェード（秒）', key: 'crossfade_sec', value: Math.sqrt(0.01 * 0.15), fraction: 0.5 },
  { label: 'クロスフェード（秒）', key: 'crossfade_sec', value: 0, fraction: 0 },
]) {
  test(`displays ${testCase.label} ${testCase.value} s on the logarithmic slider`, async ({ page }) => {
    await mockCatalog(page);
    await page.route('**/api/configuration-manager/configuration', route => route.fulfill({ json: { ...configuration, [testCase.key]: testCase.value } }));
    await page.goto('/');
    await openControlSections(page);
    const slider = page.getByRole('slider', { name: testCase.label, exact: true });
    const field = page.locator('.log-slider').filter({ has: slider });
    await expect(slider).toBeEnabled();
    await expect(slider).toHaveAttribute('aria-valuetext', `${testCase.value} s`);
    const track = await field.locator('.slider-track').boundingBox();
    const thumb = await slider.boundingBox();
    expect(track).not.toBeNull();
    expect(thumb).not.toBeNull();
    const position = (thumb!.x + thumb!.width / 2 - track!.x) / track!.width;
    expect(Math.abs(position - testCase.fraction)).toBeLessThan(0.04);
    if (testCase.value === 0) await expect(field).not.toContainText('表示範囲外');
  });
}

test('existing configuration and selected model values populate controls without writing on mount', async ({ page }) => {
  const writes: string[] = [];
  page.on('request', request => {
    if (request.method() !== 'GET') writes.push(request.method());
  });
  await mockCatalog(page);
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await expect(page.getByRole('slider', { name: '出力音量', exact: true })).toHaveAttribute('aria-valuenow', '0.65');
  await expect(page.getByRole('slider', { name: 'モニター音量', exact: true })).toHaveCount(0);
  await expect(page.getByRole('slider', { name: 'ピッチ調整', exact: true })).toHaveAttribute('aria-valuenow', '-5');
  await expect(page.getByRole('slider', { name: 'Index使用率', exact: true })).toHaveAttribute('aria-valuenow', '0.63');
  await expect(page.getByRole('slider', { name: 'フォルマント調整', exact: true })).toHaveCount(0);
  await expect(page.getByRole('radio', { name: 'RMVPE' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeDisabled();
  await expect(page.getByRole('combobox', { name: '埋め込み器', exact: true })).toHaveCount(0);
  await expect(page.getByRole('slider', { name: 'チャンクフレーム（秒）', exact: true })).toHaveAttribute('aria-valuetext', '0.3 s');
  await expect(page.getByRole('slider', { name: 'チャンクフレーム（秒）', exact: true })).toBeEnabled();
  await expect(page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true })).toHaveAttribute('aria-valuetext', '0.68 s');
  await expect(page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true })).toBeEnabled();
  await expect(page.getByRole('slider', { name: 'クロスフェード（秒）', exact: true })).toHaveAttribute('aria-valuetext', '0.1 s');
  await expect(page.getByRole('slider', { name: 'クロスフェード（秒）', exact: true })).toBeEnabled();
  const dialog = await openSettings(page);
  await expect(dialog.getByRole('radio', { name: 'サーバーモード' })).toBeChecked();
  await expect(dialog.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true })).toContainText('USB microphone (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true })).toContainText('USB speakers (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true })).toContainText('未選択');
  await expect(dialog.getByRole('combobox', { name: '入力デバイスのサンプルレート', exact: true })).toContainText('44100 Hz');
  await expect(dialog.getByRole('combobox', { name: 'モニターデバイスのサンプルレート', exact: true })).toContainText('自動');
  await expect(dialog.getByRole('combobox', { name: '優先デバイス', exact: true })).toContainText('GPU #2');
  await expect(dialog.getByRole('checkbox', { name: 'WASAPI排他モードを有効にする' })).toBeChecked();
  await expect(dialog.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toBeChecked();
  await expect(dialog.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' })).not.toBeChecked();
  await expect(dialog.getByRole('slider', { name: 'ハイパスのカットオフ', exact: true })).toHaveAttribute('aria-valuetext', '140 Hz');
  await expect(dialog.getByRole('slider', { name: 'ローパスのカットオフ', exact: true })).toHaveAttribute('aria-valuetext', '9500 Hz');
  await expect(dialog.getByRole('slider', { name: 'ノイズゲートのしきい値', exact: true })).toHaveAttribute('aria-valuetext', '-55 dB');
  await page.getByRole('button', { name: '詳細設定', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('checkbox', { name: 'リアルタイム入出力解析を有効にする' })).toBeChecked();
  await expect(page.getByRole('dialog').getByRole('checkbox', { name: 'リアルタイム音声処理解析を有効にする' })).not.toBeChecked();
  await expect(page.getByRole('dialog').getByRole('combobox', { name: '入出力解析の送信間隔' })).toContainText('0.4 s');
  await expect(page.getByRole('dialog').getByRole('combobox', { name: '音声処理解析の送信間隔' })).toContainText('2.2 s');
  for (const field of await page.getByRole('dialog').locator('input, textarea, select, [role=slider]').all()) {
    await expect(field).toBeDisabled();
  }
  expect(writes).toEqual([]);
});

test('reload reflects changed configuration and the newly selected model', async ({ page }) => {
  await mockCatalog(page);
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({
    json: { ...configuration, current_slot_index: 2, voice_changer_input_mode: 'client', audio_input_device_gain: 4.2 },
  }));
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '4.2');
  await expect(page.getByRole('slider', { name: 'ピッチ調整', exact: true })).toHaveAttribute('aria-valuenow', '3');
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'クライアントモード' })).toBeChecked();
});

test('missing fields show unknown values rather than sample defaults', async ({ page }) => {
  await mockCatalog(page);
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({ json: { current_slot_index: 7 } }));
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  await expect(page.locator('.range-field').filter({ hasText: '入力音量' }).locator('output')).toHaveText('—');
  const dialog = await openSettings(page);
  await expect(dialog.getByRole('combobox', { name: '優先デバイス', exact: true })).toContainText('—');
  await expect(dialog.getByRole('slider', { name: 'クロスフェード（秒）', exact: true })).toHaveAttribute('aria-valuetext', '—');
  await expect(dialog.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toHaveJSProperty('indeterminate', true);
});

test('failed reload clears settings and does not leave previous gains visible', async ({ page }) => {
  let online = true;
  await page.route('**/api/**', route => online ? fulfillCatalog(route) : route.abort('connectionrefused'));
  await page.route('**/model_dir/**', route => route.fulfill({ status: 404 }));
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  online = false;
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.locator('.models-panel').getByRole('alert')).toBeVisible();
  await expect(page.locator('.range-field').filter({ hasText: '入力音量' }).locator('output')).toHaveText('—');
  await expect(page.locator('.controls-column')).toContainText('設定を読み込めませんでした');
});

test('invalid setting types are rejected rather than coerced', async ({ page }) => {
  await mockCatalog(page);
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({
    json: { ...configuration, enable_high_pass_filter: 'false' },
  }));
  await page.goto('/');
  await openControlSections(page);
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('応答形式が想定と異なる');
  await expect(page.locator('.range-field').filter({ hasText: '入力音量' }).locator('output')).toHaveText('—');
});
