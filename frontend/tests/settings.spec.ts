import { test, expect, type Page } from '@playwright/test';
import { configuration, fulfillCatalog, mockCatalog } from './catalog-fixtures';

async function openSettings(page: Page) {
  await page.getByRole('button', { name: '設定', exact: true }).click();
  return page.getByRole('dialog');
}

test('existing configuration and selected model values populate disabled controls', async ({ page }) => {
  const writes: string[] = [];
  page.on('request', request => {
    if (request.method() !== 'GET') writes.push(request.method());
  });
  await mockCatalog(page);
  await page.goto('/');
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await expect(page.getByRole('slider', { name: '出力音量', exact: true })).toHaveAttribute('aria-valuenow', '0.65');
  await expect(page.getByRole('slider', { name: 'モニター音量', exact: true })).toHaveAttribute('aria-valuenow', '0.35');
  await expect(page.getByRole('slider', { name: 'ピッチ調整', exact: true })).toHaveAttribute('aria-valuenow', '-5');
  await expect(page.getByRole('slider', { name: 'インデックス調整', exact: true })).toHaveAttribute('aria-valuenow', '0.63');
  await expect(page.locator('.range-field').filter({ hasText: 'フォルマント調整' }).locator('output')).toHaveText('—');
  await expect(page.getByRole('combobox', { name: 'ピッチ推定器', exact: true })).toContainText('rmvpe');
  await expect(page.getByRole('combobox', { name: '埋め込み器', exact: true })).toContainText('hubert_base_l12');
  await expect(page.getByRole('combobox', { name: 'チャンク秒数', exact: true })).toContainText('0.3 s');
  await expect(page.getByRole('combobox', { name: '追加フレーム数', exact: true })).toContainText('0.68 s');
  const dialog = await openSettings(page);
  await expect(dialog.getByRole('combobox', { name: '音声変換入力モード', exact: true })).toContainText('サーバモード');
  await expect(dialog.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true })).toContainText('USB microphone (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true })).toContainText('USB speakers (Windows WASAPI)');
  await expect(dialog.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true })).toContainText('未選択');
  await expect(dialog.getByRole('combobox', { name: '入力デバイスのサンプルレート', exact: true })).toContainText('44100 Hz');
  await expect(dialog.getByRole('combobox', { name: 'モニターデバイスのサンプルレート', exact: true })).toContainText('自動');
  await expect(dialog.getByRole('combobox', { name: 'GPU設定', exact: true })).toContainText('GPU #2');
  await expect(dialog.getByRole('checkbox', { name: 'WASAPI排他モードを有効にする' })).toBeChecked();
  await expect(dialog.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toBeChecked();
  await expect(dialog.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' })).not.toBeChecked();
  await expect(dialog.getByRole('combobox', { name: 'ハイパスのカットオフ', exact: true })).toContainText('140 Hz');
  await expect(dialog.getByRole('combobox', { name: 'ローパスのカットオフ', exact: true })).toContainText('9500 Hz');
  await expect(dialog.getByRole('combobox', { name: 'ノイズゲートのしきい値', exact: true })).toContainText('-55 dB');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '詳細設定', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('checkbox', { name: 'リアルタイム入出力解析を有効にする' })).toBeChecked();
  await expect(page.getByRole('dialog').getByRole('checkbox', { name: 'リアルタイム音声処理解析を有効にする' })).not.toBeChecked();
  await expect(page.getByRole('dialog').getByRole('combobox', { name: '入出力解析の送信間隔' })).toContainText('0.4 s');
  await expect(page.getByRole('dialog').getByRole('combobox', { name: '音声処理解析の送信間隔' })).toContainText('2.2 s');
  for (const field of await page.locator('input, textarea, select:not(.header-actions select), [role=slider]').all()) {
    await expect(field).toBeDisabled();
  }
  expect(writes).toEqual([]);
});

test('reload reflects changed configuration and the newly selected model', async ({ page }) => {
  await mockCatalog(page);
  await page.goto('/');
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({
    json: { ...configuration, current_slot_index: 2, voice_changer_input_mode: 'client', audio_input_device_gain: 4.2 },
  }));
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '4.2');
  await expect(page.getByRole('slider', { name: 'ピッチ調整', exact: true })).toHaveAttribute('aria-valuenow', '3');
  await expect(page.getByRole('combobox', { name: 'ピッチ推定器', exact: true })).toContainText('fcpe');
  await expect(page.locator('.input-section .tag')).toHaveText('クライアントモード');
});

test('missing fields show unknown values rather than sample defaults', async ({ page }) => {
  await mockCatalog(page);
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({ json: { current_slot_index: 7 } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  await expect(page.locator('.range-field').filter({ hasText: '入力音量' }).locator('output')).toHaveText('—');
  const dialog = await openSettings(page);
  await expect(dialog.getByRole('combobox', { name: 'GPU設定', exact: true })).toContainText('—');
  await expect(dialog.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toHaveJSProperty('indeterminate', true);
});

test('failed reload clears settings and does not leave previous gains visible', async ({ page }) => {
  let online = true;
  await page.route('**/api/**', route => online ? fulfillCatalog(route) : route.abort('connectionrefused'));
  await page.route('**/model_dir/**', route => route.fulfill({ status: 404 }));
  await page.goto('/');
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
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('応答形式が想定と異なる');
  await expect(page.locator('.range-field').filter({ hasText: '入力音量' }).locator('output')).toHaveText('—');
});
