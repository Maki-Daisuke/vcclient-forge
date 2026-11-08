import { expect, test } from '@playwright/test';
import { openControlSections } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

test('saves a logarithmic value once after dragging while stopped', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  const track = page.locator('.log-slider').filter({ has: slider }).locator('.slider-track');
  await slider.scrollIntoViewIfNeeded();
  const box = (await track.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.25, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height / 2);
  expect(state.writes).toHaveLength(0);
  await page.mouse.up();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.writes).toHaveLength(1);
  expect(state.config.extra_frame_sec as number).toBeCloseTo(Math.sqrt(0.01 * 10), 1);
  expect(state.writes[0]).toMatchObject({ future_setting: { keep: [1, 2] } });
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(slider).toHaveAttribute('aria-valuetext', `${state.config.extra_frame_sec} s`);
});

test('allows precise adjustment from 0.010 to 0.100 seconds', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  await slider.press('Home');
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.extra_frame_sec).toBe(0.01);
  const track = page.locator('.log-slider').filter({ has: slider }).locator('.slider-track');
  const box = (await track.boundingBox())!;
  await page.mouse.click(box.x + box.width / 3, box.y + box.height / 2);
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.extra_frame_sec as number).toBeCloseTo(0.1, 2);
});

test('disables editing while audio is active and rechecks before saving', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  await expect(slider).toBeEnabled();
  state.active = true;
  await slider.press('End');
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('音声を停止');
  expect(state.writes).toHaveLength(0);
});

test('retains failed changes for retry', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true }).press('End');
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 503');
  state.putStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.extra_frame_sec).toBe(10);
});
