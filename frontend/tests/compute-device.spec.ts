import { expect, test } from './test-fixtures';
import { mockSession } from './session-fixtures';
import { openControlSections } from './catalog-fixtures';

async function openInference(page: import('@playwright/test').Page) {
  await page.goto('/');
  await openControlSections(page);
  return page.getByRole('combobox', { name: '優先デバイス' });
}

test('lists compute devices and saves the selection on start', async ({ page }) => {
  const state = await mockSession(page);
  const select = await openInference(page);
  await expect(select).toBeEnabled();
  await expect(select).toHaveValue('2');
  await expect(select.locator('option')).toHaveText(['CPU', '[CUDA] NVIDIA Test GPU', '[DirectML] Test GPU']);
  await select.selectOption('1');
  await expect(select).toHaveValue('1');
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect.poll(() => state.writes.length).toBeGreaterThanOrEqual(1);
  expect(state.writes[0].compute_device_id).toBe(1);
  expect(state.writes[0].future_setting).toEqual({ keep: [1, 2] });
  expect(state.sessionWrites[0].compute_device_id).toBe(1);
  await expect(select).toHaveValue('1');
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
});

test('cannot change compute device while audio is active', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const select = await openInference(page);
  await expect(select).toHaveValue('2');
  await expect(select).toBeDisabled();
  await expect(page.getByRole('button', { name: '自動選択' })).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});

test('auto-selects a device and saves it when starting', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/devices/compute/auto-select', async route => {
    expect(route.request().method()).toBe('POST');
    await pending;
    await route.fulfill({ json: { compute_device_id: 1, device: { id: 1, name: '[CUDA] NVIDIA Test GPU' } } });
  });
  const select = await openInference(page);
  await page.getByRole('button', { name: '自動選択' }).click();
  await expect(page.getByRole('button', { name: 'デバイスを確認中…' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'デバイスを確認中…' }).locator('.pending-spinner')).toBeVisible();
  await expect(select).toBeDisabled();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeDisabled();
  release();
  await expect(select).toHaveValue('1');
  await expect(page.getByRole('button', { name: '自動選択' })).toBeEnabled();
  await expect(page.getByRole('button', { name: '自動選択' }).locator('.pending-spinner')).toHaveCount(0);
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect.poll(() => state.sessionWrites.length).toBe(1);
  expect(state.writes[0].compute_device_id).toBe(1);
  expect(state.sessionWrites[0].compute_device_id).toBe(1);
});

test('keeps the previous selection when auto-selection fails', async ({ page }) => {
  const state = await mockSession(page);
  await page.route('**/api/devices/compute/auto-select', route => route.fulfill({ status: 500 }));
  const select = await openInference(page);
  await page.getByRole('button', { name: '自動選択' }).click();
  await expect(page.getByRole('alert')).toContainText('自動選択できませんでした');
  await expect(select).toHaveValue('2');
  await expect(page.getByRole('button', { name: '自動選択' })).toBeEnabled();
  expect(state.writes).toHaveLength(0);
});

test('rejects an auto-selection response for an unknown device', async ({ page }) => {
  await mockSession(page);
  await page.route('**/api/devices/compute/auto-select', route => route.fulfill({
    json: { compute_device_id: 99, device: { id: 99, name: 'Unknown device' } },
  }));
  const select = await openInference(page);
  await page.getByRole('button', { name: '自動選択' }).click();
  await expect(page.getByRole('alert')).toContainText('自動選択できませんでした');
  await expect(select).toHaveValue('2');
});

test('shows an unavailable list without hiding other settings', async ({ page }) => {
  await mockSession(page);
  await page.route('**/api/devices/compute', route => route.fulfill({ status: 503 }));
  const select = await openInference(page);
  await expect(select).toBeDisabled();
  await expect(select.locator('option:checked')).toContainText('一覧を取得できません');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
});

test('does not label an unknown selected ID as CPU or another device', async ({ page }) => {
  const state = await mockSession(page);
  state.config.compute_device_id = 99;
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
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('反映');
  expect(state.config.compute_device_id).toBe(2);
});

test('reports an invalid compute device rejected by the session endpoint', async ({ page }) => {
  const state = await mockSession(page);
  state.startStatus = 422;
  state.startErrorCode = 'invalid_compute_device';
  state.startErrorMessage = 'Compute device 1 does not exist.';
  const select = await openInference(page);
  await expect(select).toBeEnabled();
  await select.selectOption('1');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('利用できません');
  expect(state.config.compute_device_id).toBe(1);
});
