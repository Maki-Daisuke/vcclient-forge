import { openControlSections } from './catalog-fixtures';
import { test, expect, type Page } from '@playwright/test';
import { mockSession } from './session-fixtures';

async function openNoiseGate(page: Page) {
  return page.getByRole('slider', { name: 'ノイズゲートのしきい値', exact: true });
}

const saved = (page: Page) => expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');

test('updates the noise gate during native audio while retaining the complete configuration', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await openControlSections(page);
  const gate = await openNoiseGate(page);
  await expect(gate).toBeEnabled();
  await expect(gate).toHaveAttribute('aria-valuetext', '-55 dB');
  await expect(gate).toHaveAttribute('aria-valuemin', '-100');
  await expect(gate).toHaveAttribute('aria-valuemax', '0');
  await expect(page.locator('.noise-section')).not.toContainText('−100 dB 以下ではノイズゲートが無効');
  await expect(page.getByRole('checkbox', { name: 'ノイズゲートを有効にする' })).toBeChecked();
  state.config.high_pass_filter_cutoff = 188;
  await gate.press('ArrowRight');
  await saved(page);
  expect(state.config.noise_gate).toBe(-54);
  expect(state.config.high_pass_filter_cutoff).toBe(188);
  expect(state.config.future_setting).toEqual({ keep: [1, 2] });
  expect(state.operations).toEqual([]);
});

test('throttles a held key and flushes its final noise-gate value on release', async ({ page }) => {
  const state = await mockSession(page);
  await page.clock.install({ time: 0 });
  await page.goto('/');
  await openControlSections(page);
  const gate = await openNoiseGate(page);
  await expect(gate).toBeEnabled();
  await gate.focus();
  await page.clock.pauseAt(60_000);
  await page.keyboard.down('ArrowRight');
  await page.clock.runFor(1);
  await saved(page);
  for (let i = 0; i < 4; i++) await page.keyboard.down('ArrowRight');
  await page.clock.runFor(98);
  expect(state.writes).toHaveLength(1);
  await page.clock.runFor(2);
  await saved(page);
  expect(state.writes).toHaveLength(2);
  await page.keyboard.down('ArrowRight');
  await page.keyboard.up('ArrowRight');
  await page.clock.runFor(1);
  await saved(page);
  expect(state.writes).toHaveLength(3);
  expect(state.config.noise_gate).toBe(-49);
});

test('coalesces newer noise-gate and gain edits behind a slow save', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  const gate = await openNoiseGate(page);
  await gate.press('ArrowRight');
  await expect.poll(() => state.writes.length).toBe(1);
  await gate.press('End');
  await expect(gate).toHaveAttribute('aria-valuenow', '0');
  await page.getByRole('slider', { name: '入力音量', exact: true }).press('End');
  expect(state.writes).toHaveLength(1);
  state.gate = null;
  release();
  await saved(page);
  expect(state.writes).toHaveLength(2);
  expect(state.maxInFlight).toBe(1);
  expect(state.config.noise_gate).toBe(0);
  expect(state.config.audio_input_device_gain).toBe(10);
});

test('keeps failed edits for explicit retry and merges fresh settings', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const state = await mockSession(page);
  state.putStatus = 500;
  await page.goto('/');
  await openControlSections(page);
  const gate = await openNoiseGate(page);
  await gate.press('ArrowRight');
  const status = page.locator('main > .configuration-status');
  await expect(status.getByRole('alert')).toContainText('HTTP 500');
  const bounds = await status.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(812);
  await gate.press('Home');
  await expect(gate).toHaveAttribute('aria-valuenow', '-100');
  expect(state.writes).toHaveLength(1);
  state.config.high_pass_filter_cutoff = 222;
  state.putStatus = 200;
  await status.getByRole('button', { name: '保存を再試行' }).click();
  await expect(status).toHaveAttribute('data-state', 'saved');
  expect(state.config.noise_gate).toBe(-100);
  expect(state.config.high_pass_filter_cutoff).toBe(222);
});

test('missing noise-gate configuration remains unknown and disabled', async ({ page }) => {
  const state = await mockSession(page);
  delete state.config.noise_gate;
  await page.goto('/');
  await openControlSections(page);
  const gate = await openNoiseGate(page);
  await expect(gate).toBeDisabled();
  await expect(gate).toHaveAttribute('aria-valuetext', '—');
  await expect(page.getByRole('checkbox', { name: 'ノイズゲートを有効にする' })).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});

test('updates the noise gate in Client Mode', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  await page.goto('/');
  await openControlSections(page);
  const gate = await openNoiseGate(page);
  await expect(gate).toBeEnabled();
  await expect(gate).toHaveAttribute('aria-valuetext', '-55 dB');
  await gate.press('ArrowRight');
  await expect.poll(() => state.config.noise_gate).toBe(-54);
});

test('disables the gate at -100 dB and restores the previous threshold when enabled', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await openControlSections(page);
  const toggle = page.getByRole('checkbox', { name: 'ノイズゲートを有効にする' });
  const gate = await openNoiseGate(page);
  await toggle.uncheck();
  await saved(page);
  expect(state.config.noise_gate).toBe(-100);
  await expect(gate).toBeDisabled();
  await expect(gate).toHaveAttribute('aria-valuetext', '-100 dB');
  await toggle.check();
  await saved(page);
  expect(state.config.noise_gate).toBe(-55);
  await expect(gate).toBeEnabled();
});

test('treats legacy values below -100 dB as disabled without changing them on load', async ({ page }) => {
  const state = await mockSession(page);
  state.config.noise_gate = -120;
  await page.goto('/');
  await openControlSections(page);
  const toggle = page.getByRole('checkbox', { name: 'ノイズゲートを有効にする' });
  const gate = await openNoiseGate(page);
  await expect(toggle).not.toBeChecked();
  await expect(gate).toBeDisabled();
  await expect(gate).toHaveAttribute('aria-valuetext', '-100 dB');
  expect(state.writes).toHaveLength(0);
  await toggle.check();
  await saved(page);
  expect(state.config.noise_gate).toBe(-60);
});
