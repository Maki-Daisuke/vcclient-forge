import { expect, test } from './test-fixtures';
import { mockSession } from './session-fixtures';

async function confirmPassthrough(page: import('@playwright/test').Page) {
  await page.getByRole('dialog', { name: 'パススルーを有効にしますか？' }).getByRole('button', { name: '有効化' }).click();
}

test('asks before enabling and cancels without changing passthrough', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await button.click();
  const dialog = page.getByRole('dialog', { name: 'パススルーを有効にしますか？' });
  await expect(dialog).toContainText('変換前の声がそのまま出力されます。');
  await expect(dialog.getByRole('button', { name: 'キャンセル' })).toBeFocused();
  expect(state.writes).toHaveLength(0);
  await dialog.getByRole('button', { name: 'キャンセル' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(button).toBeFocused();
  await button.click();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  expect(state.config.pass_through).toBe(false);
  expect(state.writes).toHaveLength(0);
});

test('advanced setting skips confirmation and remembers the choice', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await page.getByRole('button', { name: '詳細設定', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const setting = dialog.getByRole('checkbox', { name: 'パススルー有効時に確認' });
  await expect(setting).toBeChecked();
  await setting.uncheck();
  await page.keyboard.press('Escape');
  await page.reload();
  await page.getByRole('button', { name: '詳細設定', exact: true }).click();
  await expect(setting).not.toBeChecked();
  await page.keyboard.press('Escape');
  const button = page.getByRole('button', { name: 'パススルー' });
  await button.click();
  await expect.poll(() => state.config.pass_through).toBe(true);
  await expect(page.getByRole('dialog', { name: 'パススルーを有効にしますか？' })).toHaveCount(0);
  await button.click();
  await expect.poll(() => state.config.pass_through).toBe(false);
  await page.getByRole('button', { name: '詳細設定', exact: true }).click();
  await setting.check();
  await page.keyboard.press('Escape');
  await button.click();
  await expect(page.getByRole('dialog', { name: 'パススルーを有効にしますか？' })).toBeVisible();
});

test('switches passthrough during audio and confirms the backend value', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await expect(button).toBeEnabled();
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  const inactiveColor = await button.evaluate(element => getComputedStyle(element).backgroundColor);
  await button.click();
  await confirmPassthrough(page);
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  const activeColor = await button.evaluate(element => getComputedStyle(element).backgroundColor);
  expect(activeColor).not.toBe(inactiveColor);
  await button.hover();
  await expect(button).toHaveCSS('background-color', activeColor);
  expect(state.writes[0]).toMatchObject({ pass_through: true, future_setting: { keep: [1, 2] } });
  await button.click();
  await expect(page.getByRole('dialog', { name: 'パススルーを有効にしますか？' })).toHaveCount(0);
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.pass_through).toBe(false);
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(button).toHaveAttribute('aria-pressed', 'false');
});

test('coalesces a second toggle behind an ongoing update', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await button.click();
  await confirmPassthrough(page);
  await expect.poll(() => state.writes.length).toBe(1);
  await button.click();
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  state.gate = null;
  release();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.writes.map(write => write.pass_through)).toEqual([true, false]);
  expect(state.maxInFlight).toBe(1);
});

test('retains a failed toggle for explicit retry', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 503;
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await button.click();
  await confirmPassthrough(page);
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 503');
  expect(state.config.pass_through).toBe(false);
  state.putStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.pass_through).toBe(true);
});

test('leaves passthrough disabled when its state is unavailable', async ({ page }) => {
  const state = await mockSession(page);
  delete state.config.pass_through;
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await expect(button).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});

test('switches passthrough in client mode without changing native gain controls', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await expect(button).toBeEnabled();
  await button.click();
  await confirmPassthrough(page);
  await expect.poll(() => state.config.pass_through).toBe(true);
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  await button.click();
  await expect.poll(() => state.config.pass_through).toBe(false);
});
