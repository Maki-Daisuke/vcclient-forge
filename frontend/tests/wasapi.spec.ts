import { expect, test } from '@playwright/test';
import { openControlSections } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

const label = 'WASAPI排他モードを有効にする';

test('does not display exclusive mode or sample-rate controls', async ({ page }) => {
  const state = await mockSession(page);
  state.config.wasapi_exclude_emabled = false;
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('checkbox', { name: label })).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: /サンプルレート/ })).toHaveCount(0);
  expect(state.writes).toHaveLength(0);
});

test('disables a saved exclusive setting before starting native audio', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByText('保存設定では排他モードが有効です。音声を開始する前に無効にします。')).toBeVisible();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.writes[0]).toMatchObject({ wasapi_exclude_emabled: false, future_setting: { keep: [1, 2] } });
  expect(state.operations).toEqual(['start']);
  expect(state.config.wasapi_exclude_emabled).toBe(false);
});

test('does not change exclusive settings while existing audio is running', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByText('保存設定では排他モードが有効です。音声を停止すると、次回開始時に無効になります。')).toBeVisible();
  expect(state.writes).toHaveLength(0);
});

test('does not start when disabling the saved exclusive setting fails', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 503;
  await page.goto('/');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  expect(state.operations).not.toContain('start');
  expect(state.config.wasapi_exclude_emabled).toBe(true);
});
