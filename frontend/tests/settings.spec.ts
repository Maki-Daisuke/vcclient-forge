import { openControlSections, configuration, fulfillCatalog, mockCatalog, slots } from './catalog-fixtures';
import { test, expect } from './test-fixtures';

test('positions chunk and extra durations on logarithmic sliders', async ({ page }) => {
  const chunkValue = Math.sqrt(0.05);
  const extraValue = Math.sqrt(0.01 * 2);
  await mockCatalog(page);
  await page.route(/\/api\/models(?:\?|$)/, route =>
    fulfillCatalog(route, slots.map(slot => slot.id === 'model_b' ? { ...slot, chunk_sec: chunkValue } : slot)),
  );
  await page.route('**/api/configuration-manager/configuration', route =>
    route.fulfill({ json: { ...configuration, extra_frame_sec: extraValue } }),
  );
  await page.goto('/');
  await openControlSections(page);
  for (const [label, value] of [
    ['チャンクフレーム（秒）', chunkValue],
    ['Extraフレーム（秒）', extraValue],
  ] as const) {
    const slider = page.getByRole('slider', { name: label, exact: true });
    const field = page.locator('.log-slider').filter({ has: slider });
    await expect(slider).toBeEnabled();
    await expect(slider).toHaveAttribute('aria-valuetext', `${value} s`);
    const track = await field.locator('.slider-track').boundingBox();
    const thumb = await slider.boundingBox();
    expect(track).not.toBeNull();
    expect(thumb).not.toBeNull();
    const position = (thumb!.x + thumb!.width / 2 - track!.x) / track!.width;
    expect(Math.abs(position - 0.5)).toBeLessThan(0.04);
  }
});

test('clamps and flags out-of-range chunk and extra durations', async ({ page }) => {
  await mockCatalog(page);
  await page.route(/\/api\/models(?:\?|$)/, route =>
    fulfillCatalog(route, slots.map(slot => slot.id === 'model_b' ? { ...slot, chunk_sec: 7 } : slot)),
  );
  await page.route('**/api/configuration-manager/configuration', route =>
    route.fulfill({ json: { ...configuration, extra_frame_sec: 5 } }),
  );
  await page.goto('/');
  await openControlSections(page);
  for (const [label, value] of [
    ['チャンクフレーム（秒）', 7],
    ['Extraフレーム（秒）', 5],
  ] as const) {
    const slider = page.getByRole('slider', { name: label, exact: true });
    const field = page.locator('.log-slider').filter({ has: slider });
    await expect(slider).toBeEnabled();
    await expect(slider).toHaveAttribute('aria-valuetext', `${value} s`);
    const track = await field.locator('.slider-track').boundingBox();
    const thumb = await slider.boundingBox();
    expect(track).not.toBeNull();
    expect(thumb).not.toBeNull();
    const position = (thumb!.x + thumb!.width / 2 - track!.x) / track!.width;
    expect(Math.abs(position - 1)).toBeLessThan(0.04);
    await expect(field).toContainText('表示範囲外');
  }
});

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
  await expect(page.getByRole('slider', { name: 'ピッチ調整', exact: true })).toHaveAttribute('aria-valuenow', '-5');
  await expect(page.getByRole('slider', { name: 'Index使用率', exact: true })).toHaveAttribute('aria-valuenow', '63');
  await expect(page.getByRole('slider', { name: 'Index使用率', exact: true })).toHaveAttribute('aria-valuetext', '63%');
  await expect(page.getByRole('radio', { name: 'RMVPE' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeDisabled();
  await expect(page.getByRole('slider', { name: 'チャンクフレーム（秒）', exact: true })).toHaveAttribute('aria-valuetext', '0.3 s');
  await expect(page.getByRole('slider', { name: 'チャンクフレーム（秒）', exact: true })).toBeEnabled();
  await expect(page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true })).toHaveAttribute('aria-valuetext', '0.68 s');
  await expect(page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true })).toBeEnabled();
  await expect(page.getByRole('radio', { name: 'サーバーモード' })).toBeChecked();
  await expect(page.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true })).toContainText('USB microphone (Windows WASAPI)');
  await expect(page.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true })).toContainText('USB speakers (Windows WASAPI)');
  await expect(page.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true })).toContainText('未選択');
  await expect(page.getByRole('combobox', { name: '優先デバイス', exact: true })).toHaveValue('2');
  await expect(page.getByRole('combobox', { name: '優先デバイス', exact: true }).locator('option:checked')).toHaveText('[DirectML] Test GPU');
  await expect(page.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' })).not.toBeChecked();
  await expect(page.getByRole('slider', { name: 'ハイパスのカットオフ', exact: true })).toHaveAttribute('aria-valuetext', '140 Hz');
  await expect(page.getByRole('slider', { name: 'ローパスのカットオフ', exact: true })).toHaveAttribute('aria-valuetext', '9500 Hz');
  await expect(page.getByRole('slider', { name: 'ノイズゲートのしきい値', exact: true })).toHaveAttribute('aria-valuetext', '-55 dB');
  await page.getByRole('button', { name: '詳細設定', exact: true }).click();
  const realtime = page.getByRole('dialog').getByRole('checkbox', { name: 'リアルタイム表示' });
  await expect(realtime).toBeEnabled();
  expect(await realtime.evaluate(element => (element as HTMLInputElement).indeterminate)).toBe(true);
  for (const field of await page.getByRole('dialog').locator('input, select, textarea, [role=slider]').all()) {
    if (['リアルタイム表示', 'パススルー有効時に確認'].includes((await field.locator('..').innerText()).trim())) await expect(field).toBeEnabled();
    else await expect(field).toBeDisabled();
  }
  expect(writes).toEqual([]);
});

test('reload reflects changed configuration and the newly selected model', async ({ page }) => {
  await mockCatalog(page);
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '2.7');
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({
    json: { ...configuration, model_id: 'model_a', voice_changer_input_mode: 'client', audio_input_device_gain: 4.2 },
  }));
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  // Client Mode uses its own local gain instead of the backend's server-mode gain.
  await expect(page.getByRole('slider', { name: '入力音量', exact: true })).toHaveAttribute('aria-valuenow', '1');
  await expect(page.getByRole('slider', { name: 'ピッチ調整', exact: true })).toHaveAttribute('aria-valuenow', '3');
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeChecked();
  await expect(page.getByRole('radio', { name: 'クライアントモード' })).toBeChecked();
});

test('missing fields show unknown values rather than sample defaults', async ({ page }) => {
  await mockCatalog(page);
  await page.route('**/api/configuration-manager/configuration', route => route.fulfill({ json: { model_id: 'model_b' } }));
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('heading', { name: '2. Test model B' })).toBeVisible();
  await expect(page.locator('.range-field').filter({ hasText: '入力音量' }).locator('output')).toHaveText('—');
  await expect(page.getByRole('combobox', { name: '優先デバイス', exact: true })).toContainText('—');
  await expect(page.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toHaveJSProperty('indeterminate', true);
});

test('failed reload clears settings and does not leave previous gains visible', async ({ page }) => {
  let online = true;
  await page.route('**/api/**', route => online ? fulfillCatalog(route) : route.abort('connectionrefused'));
  await page.route('**/api/models/*/icon**', route => route.fulfill({ status: 404 }));
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
