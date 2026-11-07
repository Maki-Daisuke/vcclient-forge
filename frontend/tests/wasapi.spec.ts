import { expect, test } from '@playwright/test';
import { openControlSections } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

const label = 'WASAPI排他モードを有効にする';
const status = 'main > .configuration-status';

test('updates exclusive mode while stopped and retains unrelated settings', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const checkbox = page.getByRole('checkbox', { name: label });
  await expect(checkbox).toBeChecked();
  await checkbox.uncheck();
  await expect(page.locator(status)).toHaveAttribute('data-state', 'saved');
  expect(state.writes[0]).toMatchObject({ wasapi_exclude_emabled: false, future_setting: { keep: [1, 2] } });
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(checkbox).not.toBeChecked();
});

test('disables exclusive mode while audio is running', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('checkbox', { name: label })).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});

test('checks current audio state before saving', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const checkbox = page.getByRole('checkbox', { name: label });
  await expect(checkbox).toBeEnabled();
  state.active = true;
  await checkbox.uncheck();
  await expect(page.locator(status).getByRole('alert')).toContainText('音声を停止');
  expect(state.writes).toHaveLength(0);
});

test('retains a failed change for retry', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('checkbox', { name: label }).uncheck();
  await expect(page.locator(status).getByRole('alert')).toContainText('HTTP 503');
  state.putStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await expect(page.locator(status)).toHaveAttribute('data-state', 'saved');
  expect(state.config.wasapi_exclude_emabled).toBe(false);
});
