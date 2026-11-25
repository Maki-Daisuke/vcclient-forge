import { expect, test } from './test-fixtures';
import { mockSession } from './session-fixtures';
import { openControlSections, waitForControlSection } from './catalog-fixtures';

const chunk = 'チャンクフレーム（秒）';
const extra = 'Extraフレーム（秒）';
const saved = 'main > .configuration-status';

test('shows the selected compute device when inference settings are collapsed', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  const section = page.locator('details.inference-section');
  const badge = section.locator('.control-group-summary-value');
  await expect(badge).toBeVisible();
  await expect(badge).toHaveText('[DirectML] Test GPU');
  await section.locator('summary').click();
  await waitForControlSection(page, 'inference');
  await expect(badge).toBeHidden();
  await section.getByLabel('優先デバイス').selectOption('1');
  expect(state.config.compute_device_id).toBe(2);
  await section.locator('summary').click();
  await waitForControlSection(page, 'inference', false);
  await expect(badge).toBeVisible();
  await expect(badge).toHaveText('[CUDA] NVIDIA Test GPU');
  await page.reload();
  await expect(badge).toHaveText('[DirectML] Test GPU');
});

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

test('stages inference settings while client audio is stopped', async ({ page }) => {
  const state = await mockSession(page);
  state.config.input_mode = 'client';
  await page.goto('/');
  await openControlSections(page);
  const device = page.getByLabel('優先デバイス');
  await expect(device).toBeEnabled();
  await expect(page.getByRole('group', { name: '優先デバイス', exact: true })).toHaveCount(0);
  await device.selectOption('1');
  await expect(device).toHaveValue('1');
  await expect(device).toBeEnabled();
  const chunkSlider = page.getByRole('slider', { name: chunk });
  await expect(chunkSlider).toBeEnabled();
  await chunkSlider.press('End');
  await expect(chunkSlider).toHaveAttribute('aria-valuetext', '1 s');
  await expect(chunkSlider).toBeEnabled();
  const extra = page.getByRole('slider', { name: 'Extraフレーム（秒）' });
  await extra.press('End');
  await expect(extra).toHaveAttribute('aria-valuetext', '2 s');
  await expect(extra).toBeEnabled();
  expect(state.writes).toHaveLength(0);
  expect(state.modelWrites).toHaveLength(0);
});

test('saves chunk in the selected model and retains other slot fields', async ({ page }) => {
  const state = await mockSession(page);
  const other = structuredClone(state.models.find(model => model.id === 'model_a')!);
  await page.goto('/');
  await openControlSections(page);
  const slider = page.getByRole('slider', { name: chunk });
  await slider.press('End');
  await expect(slider).toHaveAttribute('aria-valuetext', '1 s');
  expect(state.modelWrites).toHaveLength(0);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  expect(state.modelWrites).toHaveLength(1);
  expect(state.modelWrites[0]).toMatchObject({ id: 'model_b', data: { chunk_sec: 1 } });
  expect(state.models.find(model => model.id === 'model_a')).toEqual(other);
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await expect(slider).toHaveAttribute('aria-valuetext', '0.5 s');
  await page.getByRole('button', { name: 'Test model B', exact: true }).click();
  await expect(slider).toHaveAttribute('aria-valuetext', '1 s');
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(slider).toHaveAttribute('aria-valuetext', '1 s');
});

for (const [label, kind] of [[chunk, 'model'], [extra, 'configuration']] as const) {
  test(`${kind} setting stays disabled during audio and rechecks before write`, async ({ page }) => {
    const state = await mockSession(page);
    await page.goto('/');
    await openControlSections(page);
    const slider = page.getByRole('slider', { name: label });
    await expect(slider).toBeEnabled();
    state.active = true;
    await slider.press('End');
    await page.getByRole('button', { name: '開始', exact: true }).click();
    await expect(page.locator(saved).getByRole('alert')).toContainText('音声を停止');
    expect(state.writes).toHaveLength(0);
    expect(state.modelWrites).toHaveLength(0);
  });
}
