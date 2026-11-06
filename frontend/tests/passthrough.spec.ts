import { expect, test } from '@playwright/test';
import { mockSession } from './session-fixtures';

test('switches passthrough during audio and confirms the backend value', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await expect(button).toBeEnabled();
  await expect(button).toHaveAttribute('aria-pressed', 'false');
  const inactiveColor = await button.evaluate(element => getComputedStyle(element).backgroundColor);
  await button.click();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  await expect(button).toHaveAttribute('aria-pressed', 'true');
  const activeColor = await button.evaluate(element => getComputedStyle(element).backgroundColor);
  expect(activeColor).not.toBe(inactiveColor);
  await button.hover();
  await expect(button).toHaveCSS('background-color', activeColor);
  expect(state.writes[0]).toMatchObject({ pass_through: true, future_setting: { keep: [1, 2] } });
  await button.click();
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
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 503');
  expect(state.config.pass_through).toBe(false);
  state.putStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.pass_through).toBe(true);
});

test('leaves passthrough disabled when its state is unavailable or client mode is selected', async ({ page }) => {
  const state = await mockSession(page);
  delete state.config.pass_through;
  await page.goto('/');
  const button = page.getByRole('button', { name: 'パススルー' });
  await expect(button).toBeDisabled();
  state.config.pass_through = false;
  state.config.voice_changer_input_mode = 'client';
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(button).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});
