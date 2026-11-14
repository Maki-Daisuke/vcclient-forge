import { expect, test } from './test-fixtures';
import { mockSession } from './session-fixtures';
import { openControlSections } from './catalog-fixtures';

async function openInference(page: import('@playwright/test').Page) {
  await page.goto('/');
  await openControlSections(page);
  return page.getByRole('combobox', { name: '優先デバイス' });
}

test('lists compute devices and saves a selected device while stopped', async ({ page }) => {
  const state = await mockSession(page);
  const select = await openInference(page);
  await expect(select).toBeEnabled();
  await expect(select).toHaveValue('2');
  await expect(select.locator('option')).toHaveText(['CPU', '[CUDA] NVIDIA Test GPU', '[DirectML] Test GPU']);
  await select.selectOption('1');
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].gpu_device_id_int).toBe(1);
  expect(state.writes[0].future_setting).toEqual({ keep: [1, 2] });
  await expect(select).toHaveValue('1');
  await expect(select).toBeEnabled();
});

test('cannot change compute device while audio is active', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const select = await openInference(page);
  await expect(select).toHaveValue('2');
  await expect(select).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});

test('shows an unavailable list without hiding other settings', async ({ page }) => {
  await mockSession(page);
  await page.route('**/api/gpu-device-manager/devices', route => route.fulfill({ status: 503 }));
  const select = await openInference(page);
  await expect(select).toBeDisabled();
  await expect(select.locator('option:checked')).toContainText('一覧を取得できません');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
});

test('does not label an unknown selected ID as CPU or another device', async ({ page }) => {
  const state = await mockSession(page);
  state.config.gpu_device_id_int = 99;
  const select = await openInference(page);
  await expect(select.locator('option:checked')).toContainText('デバイス #99');
  await expect(select.locator('option:checked')).toHaveAttribute('disabled', '');
  await expect(select).toBeEnabled();
});

test('reports a device change that the backend rolled back', async ({ page }) => {
  const state = await mockSession(page);
  state.rollback = true;
  const select = await openInference(page);
  await expect(select).toBeEnabled();
  await select.selectOption('1');
  await expect(page.getByRole('alert')).toContainText('反映');
  expect(state.config.gpu_device_id_int).toBe(2);
});


test('reports a pipeline device that differs from the saved preference', async ({ page }) => {
  const state = await mockSession(page);
  state.gpuMismatch = true;
  const select = await openInference(page);
  await expect(select).toBeEnabled();
  await select.selectOption('1');
  await expect(page.getByRole('alert')).toContainText('反映');
  expect(state.config.gpu_device_id_int).toBe(1);
});
