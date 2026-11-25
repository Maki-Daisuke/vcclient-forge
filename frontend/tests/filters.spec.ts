import { openControlSections } from './catalog-fixtures';
import { test, expect } from './test-fixtures';
import { mockSession } from './session-fixtures';

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

test('applies filter switches and cutoffs during native audio using the complete configuration', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await openControlSections(page);
  const status = page.locator('.configuration-status');
  await page.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' }).check();
  await expect(status).toHaveAttribute('data-state', 'saved');
  await page.getByRole('slider', { name: 'ハイパスのカットオフ' }).press('ArrowRight');
  await expect(status).toHaveAttribute('data-state', 'saved');
  await page.getByRole('slider', { name: 'ローパスのカットオフ' }).press('ArrowLeft');
  await expect(status).toHaveAttribute('data-state', 'saved');
  expect(state.config.enable_low_pass_filter).toBe(true);
  expect(state.config.high_pass_filter_cutoff).toBe(141);
  expect(state.config.low_pass_filter_cutoff).toBe(9499);
  expect(state.config.future_setting).toEqual({ keep: [1, 2] });
  expect(state.operations).toEqual([]);
  expect(state.maxInFlight).toBe(1);
});

for (const scenario of [
  { name: 'inverted cutoffs', active: false, high: 140, low: 100, rate: 48000 },
  { name: 'cutoff above the effective Nyquist limit while running', active: true, high: 140, low: 9500, rate: 300 },
]) {
  test(`does not write ${scenario.name} and permits retry after correction`, async ({ page }) => {
    const state = await mockSession(page);
    state.active = scenario.active;
    state.config.high_pass_filter_cutoff = scenario.high;
    state.config.low_pass_filter_cutoff = scenario.low;
    state.inputSampleRate = scenario.rate;
    await page.goto('/');
    await openControlSections(page);
    await page.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' }).check();
    const status = page.locator('.configuration-status');
    await expect(status.getByRole('alert')).toContainText('カットオフ');
    expect(state.writes).toHaveLength(0);
    if (scenario.active) expect(state.sessionWrites).toHaveLength(0);
    state.config.low_pass_filter_cutoff = 9500;
    state.inputSampleRate = 48000;
    await status.getByRole('button', { name: '保存を再試行' }).click();
    await expect(status).toHaveAttribute('data-state', 'saved');
    expect(state.writes).toHaveLength(1);
    expect(state.config.enable_low_pass_filter).toBe(true);
  });
}

test('allows saving filter settings while stopped without requiring an active session sample rate', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' }).check();
  await expect(page.locator('.configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.enable_low_pass_filter).toBe(true);
  expect(state.sessionWrites).toHaveLength(0);
});

test('requires a model before editing filters', async ({ page }) => {
  const state = await mockSession(page);
  state.config.model_id = null;
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('checkbox', { name: 'ハイパスフィルタを有効にする' })).toBeDisabled();
  await expect(page.getByRole('slider', { name: 'ハイパスのカットオフ' })).toBeDisabled();
  await expect(page.locator('.noise-section')).toContainText('使用するモデルを選んでください');
  expect(state.writes).toHaveLength(0);
});
