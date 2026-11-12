import { expect, test } from '@playwright/test';
import { mockSession } from './session-fixtures';
import { openControlSections } from './catalog-fixtures';

const chunk = 'チャンクフレーム（秒）';
const extra = 'Extraフレーム（秒）';
const saved = 'main > .configuration-status';

test('explains inference controls are unavailable during conversion', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await openControlSections(page);
  for (const name of ['優先デバイス', chunk, extra]) {
    const group = page.getByRole('group', { name, exact: true });
    const tooltip = group.getByRole('tooltip', { includeHidden: true });
    await expect(tooltip).toHaveText('音声の停止中に変更できます。');
    await group.hover();
    await expect(tooltip).toBeVisible();
    await group.focus();
    await expect(tooltip).toBeVisible();
  }
});

test('saves inference settings while client audio is stopped', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  await page.goto('/');
  await openControlSections(page);
  const device = page.getByLabel('優先デバイス');
  await expect(device).toBeEnabled();
  await expect(page.getByRole('group', { name: '優先デバイス', exact: true })).toHaveCount(0);
  await device.selectOption('1');
  await expect.poll(() => state.config.gpu_device_id_int).toBe(1);
  await expect(device).toBeEnabled();
  const chunkSlider = page.getByRole('slider', { name: chunk });
  await expect(chunkSlider).toBeEnabled();
  await chunkSlider.press('End');
  await expect.poll(() => state.models[0].chunk_sec).toBe(5);
  await expect(chunkSlider).toBeEnabled();
  const extra = page.getByRole('slider', { name: 'Extraフレーム（秒）' });
  await extra.press('End');
  await expect.poll(() => state.config.extra_frame_sec).toBe(10);
  await expect(extra).toBeEnabled();
});

test('saves chunk in the selected model and retains other slot fields', async ({ page }) => {
  const state = await mockSession(page);
  const other = structuredClone(state.models[2]);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: chunk });
  await slider.press('End');
  await expect(page.locator(saved)).toHaveAttribute('data-state', 'saved');
  expect(state.modelWrites).toHaveLength(1);
  expect(state.modelWrites[0]).toMatchObject({ id: 7, data: { slot_index: 7, chunk_sec: 5, pitch_shift: -5 } });
  expect(state.models[2]).toEqual(other);
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await expect(page.locator(saved)).toHaveAttribute('data-state', 'saved');
  await expect(slider).toHaveAttribute('aria-valuetext', '0.5 s');
  await page.getByRole('button', { name: 'Test model B', exact: true }).click();
  await expect(page.locator(saved)).toHaveAttribute('data-state', 'saved');
  await expect(slider).toHaveAttribute('aria-valuetext', '5 s');
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(slider).toHaveAttribute('aria-valuetext', '5 s');
});

for (const [label, kind] of [[chunk, 'model'], [extra, 'configuration']] as const) {
  test(`${kind} setting is disabled while audio is active`, async ({ page }) => {
    const state = await mockSession(page);
    state.active = true;
    await page.goto('/');
    await openControlSections(page);
    await expect(page.getByRole('slider', { name: label })).toBeDisabled();
  });
  test(`${kind} setting stays disabled during audio and rechecks before write`, async ({ page }) => {
    const state = await mockSession(page);
    await page.goto('/');
    await openControlSections(page);
    const slider = page.getByRole('slider', { name: label });
    await expect(slider).toBeEnabled();
    state.active = true;
    await slider.press('End');
    await expect(page.locator(saved).getByRole('alert')).toContainText('音声を停止');
    expect(state.writes).toHaveLength(0);
    expect(state.modelWrites).toHaveLength(0);
  });
}

test('chunk save failure retains the pending model change for retry', async ({ page }) => {
  const state = await mockSession(page);
  state.modelStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('slider', { name: chunk }).press('End');
  await expect(page.locator(saved).getByRole('alert')).toContainText('HTTP 503');
  state.modelStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await expect(page.locator(saved)).toHaveAttribute('data-state', 'saved');
  expect(state.models[0].chunk_sec).toBe(5);
});
