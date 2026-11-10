import { openControlSections } from './catalog-fixtures';
import { test, expect, type Page } from '@playwright/test';
import { mockSession } from './session-fixtures';

const inputGain = (page: Page) => page.getByRole('slider', { name: '入力音量', exact: true });
const saved = (page: Page) => expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');

test('an unselected model explains the disabled Start button and selecting a card enables it', async ({ page }) => {
  const state = await mockSession(page);
  state.config.current_slot_index = -1;
  await page.goto('/');
  await openControlSections(page);
  const start = page.getByRole('button', { name: '開始', exact: true });
  await expect(start).toBeDisabled();
  await expect(start).toHaveAccessibleDescription('使用するモデルが選択されていません。画面上部のモデルカードを選んでください。');
  await expect(page.locator('#start-reason')).toBeHidden();
  await start.hover();
  await expect(page.locator('#start-reason')).toBeVisible();
  await page.mouse.move(0, 0);
  await start.focus();
  await expect(page.locator('#start-reason')).toBeVisible();
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await saved(page);
  await expect(start).toBeEnabled();
  await expect(page.locator('#start-reason')).toHaveCount(0);
  expect(state.config.current_slot_index).toBe(2);
  expect(state.operations).toEqual([]);
});

test('shows missing device guidance even when no model is selected', async ({ page }) => {
  const state = await mockSession(page);
  state.config.current_slot_index = -1;
  state.config.audio_input_device_index = -1;
  state.config.audio_output_device_index = -1;
  await page.goto('/');
  await openControlSections(page);
  const reason = page.locator('#start-reason');
  await expect(reason).toContainText('入力デバイスが未選択');
  await page.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true }).selectOption('8');
  await saved(page);
  await expect(reason).toContainText('出力デバイスが未選択');
  await page.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true }).selectOption('11');
  await saved(page);
  await expect(reason).toContainText('使用するモデルが選択されていません');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeDisabled();
});

test('saving a volume change does not move the audio meters', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  const position = () => page.locator('.performance').evaluate(element => element.getBoundingClientRect().top + window.scrollY);
  const before = await position();
  await inputGain(page).press('ArrowRight');
  await expect.poll(() => state.writes.length).toBe(1);
  expect(Math.abs((await position()) - before)).toBeLessThanOrEqual(1);
  state.gate = null;
  release();
  await saved(page);
  expect(Math.abs((await position()) - before)).toBeLessThanOrEqual(1);
});

test('an unavailable monitor explains how to unblock Start without requiring monitor output', async ({ page }) => {
  const state = await mockSession(page);
  state.config.audio_monitor_device_index = 99;
  await page.goto('/');
  await openControlSections(page);
  const start = page.getByRole('button', { name: '開始', exact: true });
  await expect(start).toBeDisabled();
  await expect(page.locator('#start-reason')).toContainText('モニターデバイスが見つかりません');
  await page.getByRole('combobox', { name: 'モニター用出力デバイス（スピーカー）', exact: true }).selectOption('-1');
  await saved(page);
  await expect(start).toBeEnabled();
  expect(state.config.audio_monitor_device_index).toBe(-1);
});

test('switches from client to server mode with the keyboard', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  await page.goto('/');
  await openControlSections(page);
  const client = page.getByRole('radio', { name: 'クライアントモード' });
  const server = page.getByRole('radio', { name: 'サーバーモード' });
  await expect(client).toBeChecked();
  await expect(client).toBeEnabled();
  await server.focus();
  await server.press('Space');
  await saved(page);
  await expect(server).toBeChecked();
  expect(state.config.voice_changer_input_mode).toBe('server');
});

test('selects a model and native devices, starts, adjusts volume, and stops using existing APIs', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('button', { name: 'Test model A', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await saved(page);
  expect(state.config.current_slot_index).toBe(2);
  await expect(page.getByRole('heading', { name: '3. Test model A' })).toBeVisible();
  const dialog = page;
  await dialog.getByText('サーバーモード', { exact: true }).click();
  await expect(dialog.getByRole('radio', { name: 'サーバーモード' })).toBeChecked();
  await saved(page);
  await dialog.getByRole('checkbox', { name: 'レガシーデバイスを表示' }).check();
  for (const [label, id, key] of [
    ['入力デバイス（マイク）', '11', 'audio_input_device_index'],
    ['出力デバイス（スピーカー）', '25', 'audio_output_device_index'],
    ['モニター用出力デバイス（スピーカー）', '11', 'audio_monitor_device_index'],
  ]) {
    await dialog.getByRole('combobox', { name: label, exact: true }).selectOption(id);
    await expect(dialog.locator('.configuration-status')).toHaveAttribute('data-state', 'saved');
    expect(state.config[key]).toBe(Number(id));
  }
  expect(state.config.audio_input_device_sample_rate).toBe(-1);
  expect(state.config.audio_output_device_sample_rate).toBe(-1);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Test model A', exact: true })).toBeDisabled();
  await expect(page.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true })).toBeDisabled();
  await expect(inputGain(page)).toBeEnabled();
  await inputGain(page).press('ArrowRight');
  await saved(page);
  expect(state.config.audio_input_device_gain).toBe(2.71);
  await page.getByRole('slider', { name: '出力音量', exact: true }).press('ArrowRight');
  await saved(page);
  expect(state.config.audio_monitor_device_gain).toBe(0.35);
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  expect(state.operations).toEqual(['start', 'stop']);
  expect(state.maxInFlight).toBe(1);
  expect(state.config.future_setting).toEqual({ keep: [1, 2] });
  expect(state.config.recording_started).toBe(false);
});

test('reads fresh full configuration before each write and preserves unrelated fields', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  await expect(inputGain(page)).toBeEnabled();
  state.config.noise_gate = -71;
  state.config.future_setting = { keep: 'changed by another client' };
  await inputGain(page).press('ArrowRight');
  await saved(page);
  expect(state.writes[0]).toEqual({ ...state.config, audio_input_device_gain: 2.71 });
  expect(state.config.noise_gate).toBe(-71);
  expect(state.config.future_setting).toEqual({ keep: 'changed by another client' });
});

test('sends during dragging at bounded intervals and flushes the final pointer value', async ({ page }) => {
  const state = await mockSession(page);
  await page.clock.install({ time: 0 });
  await page.goto('/');
  await openControlSections(page);
  await expect(inputGain(page)).toBeEnabled();
  const track = page.locator('.range-field').filter({ hasText: '入力音量' }).locator('.slider');
  await track.scrollIntoViewIfNeeded();
  await page.clock.pauseAt(60_000);
  const box = (await track.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height / 2);
  await page.mouse.down();
  await page.clock.runFor(1);
  await expect.poll(() => state.writes.length).toBe(1);
  await saved(page);
  for (const fraction of [0.3, 0.4, 0.5]) await page.mouse.move(box.x + box.width * fraction, box.y + box.height / 2);
  await page.clock.runFor(98);
  expect(state.writes).toHaveLength(1);
  await page.clock.runFor(2);
  await expect.poll(() => state.writes.length).toBe(2);
  await saved(page);
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height / 2);
  // Releasing outside the track must still flush immediately, before the next 100 ms tick.
  await page.mouse.move(box.x + box.width * 0.6, box.y - 40);
  await page.mouse.up();
  await page.clock.runFor(1);
  await saved(page);
  expect(state.writes).toHaveLength(3);
  expect(state.config.audio_input_device_gain).toBe(Number(await inputGain(page).getAttribute('aria-valuenow')));
  expect(state.operations).toEqual([]);
});

test('slow writes coalesce edits and old acknowledgements never overwrite the newest slider value', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.gate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  await inputGain(page).press('ArrowRight');
  await expect.poll(() => state.writes.length).toBe(1);
  await inputGain(page).press('End');
  await page.getByRole('slider', { name: '出力音量', exact: true }).press('Home');
  await expect(inputGain(page)).toHaveAttribute('aria-valuenow', '10');
  expect(state.writes).toHaveLength(1);
  state.gate = null;
  release();
  await saved(page);
  await expect(inputGain(page)).toHaveAttribute('aria-valuenow', '10');
  expect(state.config.audio_input_device_gain).toBe(10);
  expect(state.config.audio_output_device_gain).toBe(0);
  expect(state.writes).toHaveLength(2);
  expect(state.maxInFlight).toBe(1);
});

test('held arrow keys are throttled and key release flushes the final value', async ({ page }) => {
  const state = await mockSession(page);
  await page.clock.install({ time: 0 });
  await page.goto('/');
  await openControlSections(page);
  await expect(inputGain(page)).toBeEnabled();
  await inputGain(page).focus();
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
  expect(state.config.audio_input_device_gain).toBe(2.76);
});

test('a timed-out write remains uncertain and does not automatically resend pending edits', async ({ page }) => {
  const state = await mockSession(page);
  await page.clock.install();
  await page.route('**/api/configuration-manager/configuration', async route => {
    if (route.request().method() === 'GET') await route.fulfill({ json: state.config });
    else state.writes.push(route.request().postDataJSON());
  });
  await page.goto('/');
  await openControlSections(page);
  await inputGain(page).press('ArrowRight');
  await expect.poll(() => state.writes.length).toBe(1);
  await inputGain(page).press('End');
  await page.clock.fastForward(30_001);
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('反映済みの可能性');
  await page.clock.fastForward(1_000);
  expect(state.writes).toHaveLength(1);
  await expect(inputGain(page)).toHaveAttribute('aria-valuenow', '10');
  await page.unroute('**/api/configuration-manager/configuration');
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await saved(page);
  expect(state.writes).toHaveLength(2);
  expect(state.config.audio_input_device_gain).toBe(10);
});

test('failed saves retain the draft and retry only on request with fresh settings', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 500;
  await page.goto('/');
  await openControlSections(page);
  await inputGain(page).press('ArrowRight');
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 500');
  await inputGain(page).press('End');
  expect(state.writes).toHaveLength(1);
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeDisabled();
  state.config.noise_gate = -88;
  state.putStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await saved(page);
  expect(state.config.audio_input_device_gain).toBe(10);
  expect(state.config.noise_gate).toBe(-88);
});

test('save errors stay visible while scrolling and disappear after a successful retry', async ({ page }) => {
  const state = await mockSession(page);
  state.putStatus = 500;
  await page.goto('/');
  await openControlSections(page);
  await inputGain(page).press('ArrowRight');
  const notice = page.locator('main > .configuration-status');
  await expect(notice.getByRole('alert')).toContainText('HTTP 500');
  const position = () => notice.evaluate(element => ({ top: element.getBoundingClientRect().top, left: element.getBoundingClientRect().left }));
  const before = await position();
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  const after = await position();
  expect(Math.abs(after.top - before.top)).toBeLessThanOrEqual(1);
  expect(Math.abs(after.left - before.left)).toBeLessThanOrEqual(1);
  state.putStatus = 200;
  await notice.getByRole('button', { name: '保存を再試行' }).click();
  await saved(page);
  await expect(notice).toBeHidden();
});

test('detects silent model rollback and discard reloads the actual model', async ({ page }) => {
  const state = await mockSession(page);
  state.rollback = true;
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('反映されていません');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '変更を破棄して再読み込み' }).click();
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  expect(state.operations).toEqual([]);
});

test('start failures are visible, do not claim success, and can be retried', async ({ page }) => {
  const state = await mockSession(page);
  state.startStatus = 500;
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.locator('.transport-block').getByRole('alert')).toContainText('Test start failure');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  state.startStatus = 200;
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
  expect(state.operations).toEqual(['start', 'start']);
});

test('unknown runtime state blocks start and device edits but still permits stop', async ({ page }) => {
  const state = await mockSession(page);
  state.infoFail = true;
  await page.goto('/');
  await openControlSections(page);
  await expect(page.locator('.transport-block')).toContainText('音声の状態を取得できません');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '停止', exact: true })).not.toHaveClass(/\brunning\b/);
  await expect(page.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true })).toBeDisabled();
  state.infoFail = false;
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  expect(state.operations).toEqual(['stop']);
});

test('the combined button follows backend state changes', async ({ page }) => {
  await page.clock.install();
  const state = await mockSession(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  state.active = true;
  await page.clock.fastForward(2_100);
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toHaveClass(/\brunning\b/);
  state.active = false;
  await page.clock.fastForward(2_100);
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  await expect(page.getByRole('button', { name: '開始', exact: true })).not.toHaveClass(/\brunning\b/);
  expect(state.operations).toEqual([]);
});

test('stop waits for the in-flight gain update without racing it', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  let release!: () => void;
  state.gate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
  await inputGain(page).press('ArrowRight');
  await expect.poll(() => state.writes.length).toBe(1);
  await page.getByRole('button', { name: '停止', exact: true }).click();
  expect(state.operations).toEqual([]);
  state.gate = null;
  release();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  expect(state.operations).toEqual(['stop']);
});
