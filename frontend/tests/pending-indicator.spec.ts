import { expect, test } from '@playwright/test';
import { mockSession } from './session-fixtures';

test('shows a pending indicator on the requested model until it is confirmed', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise<void>(resolve => { release = resolve; });
  await page.goto('/');
  const model = page.getByRole('button', { name: 'Test model A', exact: true });
  await expect(model).toBeEnabled();
  await model.click();
  await expect(model.locator('.pending-indicator')).toBeVisible();
  await expect(model).toHaveAttribute('aria-busy', 'true');
  expect(state.config.current_slot_index).toBe(7);
  release();
  await expect(model.locator('.pending-indicator')).toHaveCount(0);
  await expect(model).toHaveAttribute('aria-busy', 'false');
  expect(state.config.current_slot_index).toBe(2);
});

test('shows device progress until confirmation, and stops it on failure', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise<void>(resolve => { release = resolve; });
  state.putStatus = 503;
  await page.goto('/');
  const section = page.locator('details.inference-section');
  await section.locator('summary').click();
  const field = section.locator('.select-field').filter({ has: page.getByLabel('優先デバイス') });
  const select = field.locator('select');
  await select.selectOption('1');
  await expect(field.locator('.pending-indicator')).toBeVisible();
  await expect(select).toHaveValue('1');
  expect(state.config.gpu_device_id_int).toBe(2);
  release();
  await expect(page.locator('.configuration-status').getByRole('alert')).toContainText('HTTP 503');
  await expect(field.locator('.pending-indicator')).toHaveCount(0);
  state.putStatus = 200;
  state.gate = new Promise<void>(resolve => { release = resolve; });
  await page.getByRole('button', { name: '保存を再試行' }).click();
  await expect(field.locator('.pending-indicator')).toBeVisible();
  release();
  await expect(field.locator('.pending-indicator')).toHaveCount(0);
  expect(state.config.gpu_device_id_int).toBe(1);
});

test('shows progress for an inference setting until the model update completes', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.modelGate = new Promise<void>(resolve => { release = resolve; });
  await page.goto('/');
  await page.locator('details.inference-section summary').click();
  const slider = page.getByRole('slider', { name: 'チャンクフレーム（秒）' });
  const field = page.locator('.log-slider').filter({ has: slider });
  await slider.press('End');
  await expect(field.locator('.pending-indicator')).toBeVisible();
  expect(state.models[0].chunk_sec).toBe(0.3);
  release();
  await expect(field.locator('.pending-indicator')).toHaveCount(0);
  expect(state.models[0].chunk_sec).toBe(5);
});
