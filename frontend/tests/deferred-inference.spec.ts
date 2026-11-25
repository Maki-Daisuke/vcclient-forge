import { expect, test } from './test-fixtures';
import { openControlSections } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

test('keeps stopped-only settings in the UI while saving live gains, then applies them on start', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.modelGate = new Promise<void>(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  await page.getByLabel('優先デバイス').selectOption('1');
  await page.getByRole('slider', { name: 'チャンクフレーム（秒）' }).press('End');
  await page.getByRole('slider', { name: 'Extraフレーム（秒）' }).press('End');
  expect(state.writes).toHaveLength(0);
  expect(state.modelWrites).toHaveLength(0);
  await page.getByRole('slider', { name: '入力音量', exact: true }).press('ArrowRight');
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.config.compute_device_id).toBe(2);
  expect(state.config.extra_frame_sec).toBe(0.68);
  expect(state.models.find(model => model.id === 'model_b')!.chunk_sec).toBe(0.3);
  const start = page.getByRole('button', { name: '開始', exact: true });
  await expect(start).toBeEnabled();
  await start.click();
  await expect.poll(() => state.modelWrites.length).toBe(1);
  await expect(page.getByRole('status').filter({ hasText: 'ウォームアップ中' })).toBeVisible();
  await expect(page.getByRole('tooltip', { name: 'ウォームアップ中……' })).toBeVisible();
  state.modelGate = null;
  release();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.models.find(model => model.id === 'model_b')!.chunk_sec).toBe(1);
  expect(state.config.compute_device_id).toBe(1);
  expect(state.config.extra_frame_sec).toBe(2);
  expect(state.config.input_gain).toBe(2.71);
});

test('keeps staged edits when saving at start fails', async ({ page }) => {
  const state = await mockSession(page);
  state.modelStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'チャンクフレーム（秒）' });
  await slider.press('End');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  expect(state.active).toBe(false);
  await expect(slider).toHaveAttribute('aria-valuetext', '1 s');
  state.modelStatus = 200;
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.models.find(model => model.id === 'model_b')!.chunk_sec).toBe(1);
});

test('retains staged configuration after a failed start and applies it on retry', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  const device = page.getByLabel('優先デバイス');
  const extra = page.getByRole('slider', { name: 'Extraフレーム（秒）' });
  await device.selectOption('1');
  await extra.press('End');
  expect(state.writes).toHaveLength(0);

  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  expect(state.active).toBe(false);
  expect(state.operations).not.toContain('start');
  expect(state.config.compute_device_id).toBe(2);
  expect(state.config.extra_frame_sec).toBe(0.68);
  await expect(device).toHaveValue('1');
  await expect(extra).toHaveAttribute('aria-valuetext', '2 s');

  state.putStatus = 200;
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.config.compute_device_id).toBe(1);
  expect(state.config.extra_frame_sec).toBe(2);
});

test('applies staged settings for multiple models without losing the selected model', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const chunk = page.getByRole('slider', { name: 'チャンクフレーム（秒）' });
  await chunk.press('End');
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await expect(chunk).toHaveAttribute('aria-valuetext', '0.5 s');
  await chunk.press('End');
  await page.getByRole('radio', { name: 'RMVPE' }).check();
  expect(state.modelWrites).toHaveLength(0);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.config.model_id).toBe('model_a');
  expect(state.modelWrites.map(write => write.id)).toEqual(['model_a', 'model_b']);
  expect(state.models.find(model => model.id === 'model_a')).toMatchObject({ chunk_sec: 1, pitch_estimator: 'rmvpe' });
  expect(state.models.find(model => model.id === 'model_b')).toMatchObject({ chunk_sec: 1 });
});
