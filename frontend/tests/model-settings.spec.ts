import { openControlSections } from './catalog-fixtures';
import { test, expect, type Page } from '@playwright/test';
import { mockSession } from './session-fixtures';

const pitch = (page: Page) => page.getByRole('slider', { name: 'ピッチ調整', exact: true });
const index = (page: Page) => page.getByRole('slider', { name: 'Index使用率', exact: true });
const saved = (page: Page) => expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');

async function mockEditableModel(page: Page) {
  const state = await mockSession(page);
  Object.assign(state.models[0], {
    is_f0: true, model_file: 'voice.onnx', index_file: 'voice.index',
    protect_ratio: 0.5, speakers: { 0: 'Speaker' }, future_model_setting: { keep: true },
  });
  return state;
}

test('updates pitch and index while running, preserving fresh full slot data and other models', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.active = true;
  const otherModel = structuredClone(state.models[2]);
  await page.goto('/');
  await openControlSections(page);
  await expect(pitch(page)).toBeEnabled();
  state.models[0].protect_ratio = 0.42;
  state.models[0].future_model_setting = { keep: 'newer backend value' };
  await pitch(page).press('ArrowRight');
  await saved(page);
  await index(page).press('ArrowRight');
  await saved(page);
  expect(state.modelWrites.map(write => write.id)).toEqual([7, 7]);
  expect(state.modelWrites[1].data).toMatchObject({
    slot_index: 7, voice_changer_type: 'RVC', pitch_shift: -4, index_ratio: 0.64,
    model_file: 'voice.onnx', index_file: 'voice.index', protect_ratio: 0.42,
    speakers: { 0: 'Speaker' }, future_model_setting: { keep: 'newer backend value' },
  });
  expect(state.models[2]).toEqual(otherModel);
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '-4');
  await expect(index(page)).toHaveAttribute('aria-valuenow', '0.64');
});

test('coalesces model edits with volume writes in one queue without stale slider acknowledgements', async ({ page }) => {
  const state = await mockEditableModel(page);
  let release!: () => void;
  state.modelGate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  await pitch(page).press('ArrowRight');
  await expect.poll(() => state.modelWrites.length).toBe(1);
  await pitch(page).press('End');
  await index(page).press('Home');
  await page.getByRole('slider', { name: '入力音量', exact: true }).press('End');
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '24');
  await expect(page.getByRole('button', { name: '再読み込み', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Test model A', exact: true })).toBeDisabled();
  expect(state.writes).toHaveLength(0);
  state.modelGate = null;
  release();
  await saved(page);
  expect(state.maxInFlight).toBe(1);
  expect(state.modelWrites).toHaveLength(2);
  expect(state.writes).toHaveLength(1);
  expect(state.models[0].pitch_shift).toBe(24);
  expect(state.models[0].index_ratio).toBe(0);
  expect(state.config.audio_input_device_gain).toBe(10);
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '24');
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await saved(page);
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '3');
  await expect(index(page)).toHaveAttribute('aria-valuenow', '0.25');
  expect(state.models[2].pitch_shift).toBe(3);
});

test('throttles index dragging and flushes the final value on release', async ({ page }) => {
  const state = await mockEditableModel(page);
  await page.clock.install({ time: 0 });
  await page.goto('/');
  await openControlSections(page);
  await expect(index(page)).toBeEnabled();
  const track = page.locator('.range-field').filter({ hasText: 'Index使用率' }).locator('.slider');
  await track.scrollIntoViewIfNeeded();
  await page.clock.pauseAt(60_000);
  const box = (await track.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.2, box.y + box.height / 2);
  await page.mouse.down();
  await page.clock.runFor(1);
  await saved(page);
  for (const fraction of [0.3, 0.4, 0.5]) await page.mouse.move(box.x + box.width * fraction, box.y + box.height / 2);
  await page.clock.runFor(98);
  expect(state.modelWrites).toHaveLength(1);
  await page.clock.runFor(2);
  await saved(page);
  expect(state.modelWrites).toHaveLength(2);
  await page.mouse.move(box.x + box.width * 0.6, box.y - 40);
  await page.mouse.up();
  await page.clock.runFor(1);
  await saved(page);
  expect(state.modelWrites).toHaveLength(3);
  expect(state.models[0].index_ratio).toBe(Number(await index(page).getAttribute('aria-valuenow')));
});

test('retains a failed model draft and retries the same slot against fresh data', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.modelStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  await pitch(page).press('ArrowRight');
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 503');
  await pitch(page).press('End');
  await expect(page.getByRole('button', { name: 'Test model A', exact: true })).toBeDisabled();
  expect(state.modelWrites).toHaveLength(1);
  state.models[0].description = 'New backend description';
  state.modelStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await saved(page);
  expect(state.modelWrites[1]).toMatchObject({ id: 7, data: { slot_index: 7, pitch_shift: 24, description: 'New backend description' } });
  expect(state.models[0].description).toBe('New backend description');
  expect(state.writes).toHaveLength(0);
});

test('detects an unapplied model update and discards back to confirmed settings', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.modelRollback = true;
  await page.goto('/');
  await openControlSections(page);
  await pitch(page).press('ArrowRight');
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('反映されていません');
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '-4');
  await page.getByRole('button', { name: '変更を破棄して再読み込み' }).click();
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '-5');
  await expect(page.getByRole('button', { name: 'Test model A', exact: true })).toBeEnabled();
});

test('rejects a mismatched slot ID before PUT can affect another model', async ({ page }) => {
  const state = await mockEditableModel(page);
  await page.route('**/api/slot-manager/slots/7', route => route.fulfill({ json: state.models[2] }));
  await page.goto('/');
  await openControlSections(page);
  await pitch(page).press('ArrowRight');
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('応答形式');
  expect(state.modelWrites).toHaveLength(0);
  expect(state.writes).toHaveLength(0);
});

test('unsupported pitch and missing index remain disabled with an explanation', async ({ page }) => {
  await mockSession(page);
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  await expect(pitch(page)).toBeDisabled();
  await expect(index(page)).toBeDisabled();
  await expect(page.locator('.voice-settings')).toContainText('このモデルはピッチ調整に対応していません');
  await expect(page.locator('.voice-settings')).toContainText('Indexファイルが設定されていません');
  const indexLabel = page.locator('.voice-settings .range-label-text').filter({ has: page.getByRole('heading', { name: 'Index使用率' }) });
  await expect(indexLabel).toContainText('Indexファイルが設定されていません');
});

test('stop waits for the active model write', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.active = true;
  let release!: () => void;
  state.modelGate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await openControlSections(page);
  await pitch(page).press('ArrowRight');
  await expect.poll(() => state.modelWrites.length).toBe(1);
  await page.getByRole('button', { name: '停止', exact: true }).click();
  expect(state.operations).toEqual([]);
  state.modelGate = null;
  release();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  expect(state.operations).toEqual(['stop']);
});
