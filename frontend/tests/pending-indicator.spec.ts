import { expect, test } from './test-fixtures';
import { mockSession } from './session-fixtures';
import { waitForControlSection } from './catalog-fixtures';

test('shows warmup while the selected model is applied on start', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise<void>(resolve => { release = resolve; });
  await page.goto('/');
  const model = page.getByRole('button', { name: 'Test model A', exact: true });
  await expect(model).toBeEnabled();
  await model.click();
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'ウォームアップ中' })).toBeVisible();
  expect(state.config.current_slot_index).toBe(7);
  release();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.config.current_slot_index).toBe(2);
});

test('shows warmup while the selected device is applied and allows retry after failure', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise<void>(resolve => { release = resolve; });
  state.putStatus = 503;
  await page.goto('/');
  const section = page.locator('details.inference-section');
  await section.locator('summary').click();
  await waitForControlSection(page, 'inference');
  const field = section.locator('.select-field').filter({ has: page.getByLabel('優先デバイス') });
  const select = field.locator('select');
  await select.selectOption('1');
  await expect(select).toHaveValue('1');
  expect(state.config.gpu_device_id_int).toBe(2);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'ウォームアップ中' })).toBeVisible();
  release();
  await expect(page.locator('.configuration-status').getByRole('alert')).toContainText('HTTP 503');
  state.putStatus = 200;
  state.gate = new Promise<void>(resolve => { release = resolve; });
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'ウォームアップ中' })).toBeVisible();
  release();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.config.gpu_device_id_int).toBe(1);
});

test('shows warmup for an inference setting until the model update completes', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.modelGate = new Promise<void>(resolve => { release = resolve; });
  await page.goto('/');
  await page.locator('details.inference-section summary').click();
  await waitForControlSection(page, 'inference');
  const slider = page.getByRole('slider', { name: 'チャンクフレーム（秒）' });
  await slider.press('End');
  expect(state.models[0].chunk_sec).toBe(0.3);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'ウォームアップ中' })).toBeVisible();
  release();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.models[0].chunk_sec).toBe(1);
});
