import { openControlSections } from './catalog-fixtures';
import { test, expect, type Page } from './test-fixtures';
import { mockSession } from './session-fixtures';

const pitch = (page: Page) => page.getByRole('slider', { name: 'ピッチ調整', exact: true });
const index = (page: Page) => page.getByRole('slider', { name: 'Index使用率', exact: true });
const saved = (page: Page) => expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');

async function mockEditableModel(page: Page) {
  const state = await mockSession(page);
  Object.assign(state.models.find(model => model.id === 'model_b')!, {
    supports_f0: true, has_index: true,
    future_model_setting: { keep: true },
  });
  return state;
}

test('stages the selected model pitch estimator and applies it on start', async ({ page }) => {
  const state = await mockEditableModel(page);
  let release!: () => void;
  state.modelGate = new Promise(resolve => { release = resolve; });
  await page.goto('/');
  await expect(page.locator('.voice-settings h3')).toHaveText(['ピッチ推定器', 'ピッチ調整', 'Index使用率']);
  await expect(page.getByText('ピッチ推定器は音声の停止中に変更できます。')).toHaveCount(0);
  const rmvpe = page.getByRole('radio', { name: 'RMVPE' });
  const fcpe = page.getByRole('radio', { name: 'FCPE' });
  await expect(rmvpe).toBeChecked();
  await expect(fcpe).toBeEnabled();
  await fcpe.check();
  expect(state.modelWrites).toHaveLength(0);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect.poll(() => state.modelWrites.length).toBe(1);
  await expect(fcpe).toBeDisabled();
  state.modelGate = null;
  release();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  await expect(fcpe).toBeChecked();
  await expect(fcpe).toBeDisabled();
  expect(state.modelWrites[0]).toEqual({ id: 'model_b', data: { pitch_estimator: 'fcpe' } });
  expect(state.models.find(model => model.id === 'model_b')).toMatchObject({ pitch_estimator: 'fcpe', future_model_setting: { keep: true } });
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(fcpe).toBeChecked();
});

test('keeps pitch estimator disabled during audio conversion', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.active = true;
  await page.goto('/');
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeDisabled();
  const tooltip = page.getByRole('tooltip', { name: 'ピッチ推定器は音声の停止中に変更できます。' });
  await expect(tooltip).toBeHidden();
  const group = page.locator('.estimator-wrapper');
  await group.hover();
  await expect(tooltip).toBeVisible();
  await page.mouse.move(0, 0);
  await group.focus();
  await expect(tooltip).toBeVisible();
  expect(state.modelWrites).toHaveLength(0);
});

test('switches the pitch estimator in client mode while stopped', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.config.input_mode = 'client';
  await page.goto('/');
  const fcpe = page.getByRole('radio', { name: 'FCPE' });
  await expect(fcpe).toBeEnabled();
  await fcpe.check();
  await expect(fcpe).toBeChecked();
  expect(state.modelWrites).toHaveLength(0);
});

test('shows Index usage as a percentage while saving the backend ratio', async ({ page }) => {
  const state = await mockEditableModel(page);
  await page.goto('/');
  const field = page.locator('.range-field').filter({ hasText: 'Index使用率' });
  await expect(field.locator('output')).toHaveText('63%');
  await expect(field.locator('.range-limits span')).toHaveText(['0', '100']);
  await expect(index(page)).toHaveAttribute('aria-valuetext', '63%');
  await index(page).press('ArrowRight');
  await saved(page);
  await expect(field.locator('output')).toHaveText('64%');
  expect(state.models.find(model => model.id === 'model_b')!.index_ratio).toBe(0.64);
});

test('rechecks stopped audio before writing a pitch estimator', async ({ page }) => {
  const state = await mockEditableModel(page);
  await page.goto('/');
  const fcpe = page.getByRole('radio', { name: 'FCPE' });
  await expect(fcpe).toBeEnabled();
  state.active = true;
  await fcpe.check();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('音声を停止');
  expect(state.modelWrites).toHaveLength(0);
});

test('reports an async startup failure when starting with an updated pitch estimator', async ({ page }) => {
  const state = await mockEditableModel(page);
  let release!: () => void;
  state.sessionGate = new Promise(resolve => { release = resolve; });
  state.asyncStartError = { code: 'session_start_failed', message: 'FCPE initialization failed' };
  await page.goto('/');
  await page.getByRole('radio', { name: 'FCPE' }).check();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'ウォームアップ中' })).toBeVisible();
  release();
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('FCPE initialization failed');
  expect(state.models.find(model => model.id === 'model_b')!.pitch_estimator).toBe('fcpe');
  state.sessionGate = null;
  state.asyncStartError = null;
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeChecked();
});

test('updates pitch and index while running, preserving unrelated model fields and other models', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.active = true;
  const modelA = structuredClone(state.models.find(model => model.id === 'model_a')!);
  const modelB = state.models.find(model => model.id === 'model_b')!;
  await page.goto('/');
  await openControlSections(page);
  await expect(pitch(page)).toBeEnabled();
  modelB.future_model_setting = { keep: 'newer backend value' };
  await pitch(page).press('ArrowRight');
  await saved(page);
  await index(page).press('ArrowRight');
  await saved(page);
  expect(state.modelWrites.map(write => write.id)).toEqual(['model_b', 'model_b']);
  expect(state.modelWrites[1].data).toEqual({ index_ratio: 0.64 });
  expect(state.sessionWrites.map(write => ({ pitch_shift: write.pitch_shift, index_ratio: write.index_ratio }))).toEqual([
    { pitch_shift: -4, index_ratio: 0.63 },
    { pitch_shift: -4, index_ratio: 0.64 },
  ]);
  expect(modelB).toMatchObject({
    id: 'model_b',
    pitch_shift: -4,
    index_ratio: 0.64,
    future_model_setting: { keep: 'newer backend value' },
  });
  expect(state.models.find(model => model.id === 'model_a')).toEqual(modelA);
  expect(state.writes).toHaveLength(0);
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '-4');
  await expect(index(page)).toHaveAttribute('aria-valuenow', '64');
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
  const modelB = state.models.find(model => model.id === 'model_b')!;
  expect(modelB.pitch_shift).toBe(24);
  expect(modelB.index_ratio).toBe(0);
  expect(state.config.input_gain).toBe(10);
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '24');
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await saved(page);
  await expect(pitch(page)).toHaveAttribute('aria-valuenow', '3');
  await expect(index(page)).toHaveAttribute('aria-valuenow', '25');
  expect(state.models.find(model => model.id === 'model_a')!.pitch_shift).toBe(3);
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
  expect(state.models.find(model => model.id === 'model_b')!.index_ratio).toBe(Number(await index(page).getAttribute('aria-valuenow')) / 100);
});

test('retains a failed model draft and retries the same model against fresh data', async ({ page }) => {
  const state = await mockEditableModel(page);
  state.modelStatus = 503;
  await page.goto('/');
  await openControlSections(page);
  await pitch(page).press('ArrowRight');
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 503');
  await pitch(page).press('End');
  await expect(page.getByRole('button', { name: 'Test model A', exact: true })).toBeDisabled();
  expect(state.modelWrites).toHaveLength(1);
  const modelB = state.models.find(model => model.id === 'model_b')!;
  modelB.name = 'New backend name';
  state.modelStatus = 200;
  await page.getByRole('button', { name: '保存を再試行', exact: true }).click();
  await saved(page);
  expect(state.modelWrites[1]).toEqual({ id: 'model_b', data: { pitch_shift: 24 } });
  expect(modelB.name).toBe('New backend name');
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

test('rejects a mismatched model ID before PUT can affect another model', async ({ page }) => {
  const state = await mockEditableModel(page);
  await page.route('**/api/models/model_b', route => route.fulfill({ json: state.models[0] }));
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
  await expect(page.getByRole('heading', { name: '2. Test model B' })).toBeVisible();
  await expect(pitch(page)).toBeDisabled();
  await expect(index(page)).toBeDisabled();
  const pitchGroup = page.getByRole('group', { name: 'ピッチ調整', exact: true });
  const indexGroup = page.getByRole('group', { name: 'Index使用率', exact: true });
  const pitchTooltip = pitchGroup.locator('[role="tooltip"]');
  const indexTooltip = indexGroup.locator('[role="tooltip"]');
  await expect(pitchTooltip).toBeHidden();
  await expect(indexTooltip).toBeHidden();
  await pitchGroup.hover();
  await expect(pitchTooltip).toBeVisible();
  await expect(pitchTooltip).toContainText('このモデルはピッチ調整に対応していません');
  await indexGroup.hover();
  await expect(pitchTooltip).toBeHidden();
  await expect(indexTooltip).toBeVisible();
  await expect(indexTooltip).toContainText('Indexファイルが設定されていません');
  await page.mouse.move(0, 0);
  await indexGroup.focus();
  await expect(indexTooltip).toBeVisible();
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
