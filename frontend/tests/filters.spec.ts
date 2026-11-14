import { openControlSections } from './catalog-fixtures';
import { test, expect, type Page } from './test-fixtures';
import { mockSession } from './session-fixtures';

async function openFilters(page: Page) {
  return page;
}

for (const filter of [
  { heading: 'ハイパスフィルタ', checkbox: 'ハイパスフィルタを有効にする', slider: 'ハイパスのカットオフ', initiallyEnabled: true },
  { heading: 'ローパスフィルタ', checkbox: 'ローパスフィルタを有効にする', slider: 'ローパスのカットオフ', initiallyEnabled: false },
]) {
  test(`${filter.heading} cutoff follows its enable checkbox`, async ({ page }) => {
    await mockSession(page);
    await page.goto('/');
    await openControlSections(page);
    await expect(page.getByRole('heading', { name: filter.heading, exact: true })).toBeVisible();
    const checkbox = page.getByRole('checkbox', { name: filter.checkbox });
    const slider = page.getByRole('slider', { name: filter.slider });
    if (filter.initiallyEnabled) {
      await expect(slider).toBeEnabled();
      await checkbox.uncheck();
      await expect(slider).toBeDisabled();
      await checkbox.check();
      await expect(slider).toBeEnabled();
    } else {
      await expect(slider).toBeDisabled();
      await checkbox.check();
      await expect(slider).toBeEnabled();
      await checkbox.uncheck();
      await expect(slider).toBeDisabled();
    }
  });
}

for (const width of [1280, 375]) for (const active of [false, true]) test(`keeps the background input panel in place while a cutoff is saved (${width}px, audio ${active ? 'running' : 'stopped'})`, async ({ page }) => {
  await page.setViewportSize({ width, height: 812 });
  const state = await mockSession(page);
  state.active = active;
  let release!: () => void;
  state.gate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('button', { name: active ? '停止' : '開始', exact: true })).toBeEnabled();
  const dialog = await openFilters(page);
  const slider = dialog.getByRole('slider', { name: 'ハイパスのカットオフ', exact: true });
  await slider.scrollIntoViewIfNeeded();
  const position = () => page.locator('.input-section').evaluate(el => el.getBoundingClientRect().top + window.scrollY);
  const before = await position();
  await slider.press('ArrowRight');
  await expect.poll(() => state.writes.length).toBe(1);
  await expect(dialog.locator('.configuration-status')).toHaveAttribute('data-state', 'pending');
  expect(Math.abs(await position() - before)).toBeLessThanOrEqual(1);
  state.gate = null;
  release();
  await expect(dialog.locator('.configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(Math.abs(await position() - before)).toBeLessThanOrEqual(1);
});

test('applies filter switches and cutoffs during native audio using the complete configuration', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await openControlSections(page);
  const dialog = await openFilters(page);
  const status = dialog.locator('.configuration-status');
  await dialog.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' }).check();
  await expect(status).toHaveAttribute('data-state', 'saved');
  await dialog.getByRole('slider', { name: 'ハイパスのカットオフ' }).press('ArrowRight');
  await expect(status).toHaveAttribute('data-state', 'saved');
  await dialog.getByRole('slider', { name: 'ローパスのカットオフ' }).press('ArrowLeft');
  await expect(status).toHaveAttribute('data-state', 'saved');
  expect(state.config.enable_low_pass_filter).toBe(true);
  expect(state.config.high_pass_filter_cutoff).toBe(141);
  expect(state.config.low_pass_filter_cutoff).toBe(9499);
  expect(state.config.future_setting).toEqual({ keep: [1, 2] });
  expect(state.operations).toEqual([]);
  expect(state.maxInFlight).toBe(1);
});

for (const scenario of [
  { name: 'inverted cutoffs', high: 140, low: 100, rate: 48000 },
  { name: 'cutoff above the effective limit', high: 140, low: 9500, rate: 300 },
  { name: 'unavailable sample rate', high: 140, low: 9500, rate: -1 },
]) {
  test(`does not write ${scenario.name} and permits retry after correction`, async ({ page }) => {
    const state = await mockSession(page);
    state.config.high_pass_filter_cutoff = scenario.high;
    state.config.low_pass_filter_cutoff = scenario.low;
    state.config.input_sample_rate = scenario.rate;
    await page.goto('/');
  await openControlSections(page);
    const dialog = await openFilters(page);
    await dialog.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' }).check();
    const status = dialog.locator('.configuration-status');
    await expect(status.getByRole('alert')).toContainText('サンプルレート');
    expect(state.writes).toHaveLength(0);
    state.config.low_pass_filter_cutoff = 9500;
    state.config.input_sample_rate = 48000;
    await status.getByRole('button', { name: '保存を再試行' }).click();
    await expect(status).toHaveAttribute('data-state', 'saved');
    expect(state.writes).toHaveLength(1);
    expect(state.config.enable_low_pass_filter).toBe(true);
  });
}

test('a missing filter value remains unknown and disabled', async ({ page }) => {
  const state = await mockSession(page);
  delete state.config.enable_high_pass_filter;
  delete state.config.high_pass_filter_cutoff;
  await page.goto('/');
  await openControlSections(page);
  const dialog = await openFilters(page);
  await expect(dialog.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toBeDisabled();
  await expect(dialog.getByRole('slider', { name: 'ハイパスのカットオフ' })).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});

test('does not use audio information belonging to a different model', async ({ page }) => {
  const state = await mockSession(page);
  await page.route('**/api/voice-changer-manager/information', route => route.fulfill({
    json: { voice_changer_information: { slot_index: 2, input_sample_rate: 48000, output_sample_rate: 48000 } },
  }));
  await page.goto('/');
  await openControlSections(page);
  const dialog = await openFilters(page);
  await dialog.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' }).check();
  await expect(dialog.locator('.configuration-status').getByRole('alert')).toContainText('サンプルレート');
  expect(state.writes).toHaveLength(0);
});

test('requires a model before editing filters', async ({ page }) => {
  const state = await mockSession(page);
  state.config.current_slot_index = -1;
  await page.goto('/');
  await openControlSections(page);
  const dialog = await openFilters(page);
  await expect(dialog.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toBeDisabled();
  await expect(dialog.getByRole('slider', { name: 'ハイパスのカットオフ' })).toBeDisabled();
  await expect(page.locator('.noise-section')).toContainText('使用するモデルを選んでください');
  expect(state.writes).toHaveLength(0);
});
