import { expect, test } from './test-fixtures';
import { openControlSections } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

test('keeps logarithmic Extra edits locally until Start', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  const track = page.locator('.log-slider').filter({ has: slider }).locator('.slider-track');
  await slider.scrollIntoViewIfNeeded();
  const box = (await track.boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height / 2);
  await expect.poll(async () => Number((await slider.getAttribute('aria-valuetext'))?.split(' ')[0])).toBeCloseTo(Math.sqrt(0.01 * 2), 2);
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.config.extra_frame_sec as number).toBeCloseTo(Math.sqrt(0.01 * 2), 2);
  expect(state.writes[0]).toMatchObject({ future_setting: { keep: [1, 2] } });
});

test('allows precise local adjustment from 0.010 to 0.100 seconds', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  await slider.press('Home');
  await expect(slider).toHaveAttribute('aria-valuetext', '0.01 s');
  const track = page.locator('.log-slider').filter({ has: slider }).locator('.slider-track');
  const box = (await track.boundingBox())!;
  await page.mouse.click(box.x + box.width * Math.log(0.1 / 0.01) / Math.log(2 / 0.01), box.y + box.height / 2);
  await expect.poll(async () => Number((await slider.getAttribute('aria-valuetext'))?.split(' ')[0])).toBeCloseTo(0.1, 2);
  expect(state.writes).toHaveLength(0);
});

test('rechecks audio is stopped before saving staged Extra', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  await slider.press('End');
  state.active = true;
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('音声を停止');
  expect(state.writes).toHaveLength(0);
});

test('retains staged Extra after a failed start for retry', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  await slider.press('End');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 503');
  await expect(slider).toHaveAttribute('aria-valuetext', '2 s');
  state.putStatus = 200;
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.config.extra_frame_sec).toBe(2);
});

test('preserves and displays a saved value above the slider range', async ({ page }) => {
  const state = await mockSession(page);
  state.config.extra_frame_sec = 5;
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: 'Extraフレーム（秒）', exact: true });
  const field = page.locator('.log-slider').filter({ has: slider });
  await expect(slider).toHaveAttribute('aria-valuetext', '5 s');
  await expect(slider).toHaveAttribute('aria-valuemax', '2');
  await expect(field).toContainText('表示範囲外');
  await slider.press('Home');
  await expect(slider).toHaveAttribute('aria-valuetext', '0.01 s');
  expect(state.writes).toHaveLength(0);
});
