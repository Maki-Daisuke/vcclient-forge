import { test, expect } from '@playwright/test';
import { slots, fulfillCatalog, mockCatalog } from './catalog-fixtures';

test.beforeEach(async ({ page }) => {
  await page.route('**/model_dir/**', route => route.fulfill({ status: 404 }));
});

test('renders models, metadata, and the selected portrait using sparse slot IDs', async ({ page }) => {
  await mockCatalog(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'モデル選択 保存済み 2 枠' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  await expect(page.locator('.model-card')).toHaveCount(2);
  await expect(page.locator('.model-name')).toHaveText(['Test model A', 'Test model B']);
  await expect(page.locator('.model-card[aria-current=true]')).toHaveAccessibleName('Test model B');
  await expect(page.locator('.models-panel')).not.toContainText('Description of the selected model');
  await expect(page.locator('.tags')).toContainText('pth v1');
  await expect(page.locator('.tags')).toContainText('non-f0');
  await expect(page.locator('.portrait img')).toHaveAttribute('src', '/model_dir/7/portrait%20%231.png');
  await expect(page.locator('.models-panel .count')).toHaveText('保存済み 2 枠');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('textbox', { name: '名前', exact: true })).toHaveValue('Test model B');
  await expect(page.getByRole('dialog').getByRole('textbox', { name: '説明', exact: true })).toHaveCount(0);
});

test('shows loading until both the slot list and the selection arrive', async ({ page }) => {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/**', async route => {
    if (route.request().url().endsWith('/configuration')) await pending;
    await fulfillCatalog(route);
  });
  await page.goto('/');
  await expect(page.locator('.models-panel .catalog-message[role=status]')).toContainText('モデル情報を読み込んでいます');
  await expect(page.locator('.model-card')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '再読み込み', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
});

test('empty slots do not become fake installed models', async ({ page }) => {
  await page.route('**/api/**', route => fulfillCatalog(route, [{ slot_index: 0, voice_changer_type: null }], 0));
  await page.goto('/');
  await expect(page.locator('.models-panel .catalog-message[role=status]')).toHaveText('保存されているモデルはありません。モデルをアップロードしてください。');
  await expect(page.locator('.model-card')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'モデルが選択されていません' })).toBeVisible();
  await expect(page.getByRole('button', { name: '編集', exact: true })).toBeDisabled();
  await expect(page.locator('.portrait img')).toHaveCount(0);
  await expect(page.locator('.model-message')).toHaveCount(0);
});

test('a missing selected slot does not select the first model', async ({ page }) => {
  await page.route('**/api/**', route => fulfillCatalog(route, slots, 99));
  await page.goto('/');
  await expect(page.locator('.model-message')).toContainText('スロット 100');
  await expect(page.locator('.model-card')).toHaveCount(2);
  await expect(page.locator('.model-card[aria-current=true]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '編集', exact: true })).toBeDisabled();
});

test('network failure clears old models and reload recovers the current selection', async ({ page }) => {
  let online = true;
  let selectedId = 7;
  await page.route('**/api/**', route => online ? fulfillCatalog(route, slots, selectedId) : route.abort('connectionrefused'));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
  online = false;
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('バックエンドに接続できません');
  await expect(page.locator('.model-card')).toHaveCount(0);
  await expect(page.locator('.model-message')).toHaveCount(0);
  await expect(page.locator('.portrait img')).toHaveCount(0);
  online = true;
  selectedId = 2;
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.getByRole('heading', { name: '3. Test model A' })).toBeVisible();
  await expect(page.locator('.models-panel').getByRole('alert')).toHaveCount(0);
});

for (const invalid of [
  { name: 'HTML in place of JSON', response: { contentType: 'text/html', body: '<html>wrong server</html>' } },
  { name: 'an unexpected list envelope', response: { json: { slots } } },
  { name: 'a nonnumeric ID', response: { json: [{ ...slots[0], slot_index: '7' }] } },
  { name: 'duplicate IDs', response: { json: [slots[0], slots[0]] } },
]) {
  test(`rejects ${invalid.name}`, async ({ page }) => {
    await page.route('**/api/**', route => route.request().url().endsWith('/slots')
      ? route.fulfill(invalid.response) : fulfillCatalog(route));
    await page.goto('/');
    await expect(page.locator('.models-panel').getByRole('alert')).toContainText('応答形式が想定と異なる');
    await expect(page.locator('.model-card')).toHaveCount(0);
  });
}

test('a failed configuration request does not publish a partial list', async ({ page }) => {
  await page.route('**/api/**', route => route.request().url().endsWith('/configuration')
    ? route.fulfill({ status: 503 }) : fulfillCatalog(route));
  await page.goto('/');
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('HTTP 503');
  await expect(page.locator('.model-card')).toHaveCount(0);
});

test('an invalid current model ID does not silently choose a model', async ({ page }) => {
  await page.route('**/api/**', route => route.request().url().endsWith('/configuration')
    ? route.fulfill({ json: { current_slot_index: '7' } }) : fulfillCatalog(route));
  await page.goto('/');
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('応答形式が想定と異なる');
  await expect(page.locator('.model-card')).toHaveCount(0);
});

test('hung requests time out and can be retried', async ({ page }) => {
  await page.clock.install();
  await page.route('**/api/**', () => {});
  await page.goto('/');
  await expect(page.locator('.models-panel .catalog-message[role=status]')).toContainText('モデル情報を読み込んでいます');
  await page.clock.fastForward(8_001);
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('応答が間に合いませんでした');
  await page.unroute('**/api/**');
  await mockCatalog(page);
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.getByRole('heading', { name: '8. Test model B' })).toBeVisible();
});

test('broken images use a placeholder and pending or broken slots are labeled', async ({ page }) => {
  const states = [
    ...slots,
    { slot_index: 13, voice_changer_type: 'RESERVED_FOR_SAMPLE', name: 'Pending model', progress: 0.5 },
    { slot_index: 18, voice_changer_type: 'BROKEN', name: 'Broken model' },
  ];
  await page.route('**/api/**', route => fulfillCatalog(route, states));
  await page.route('**/model_dir/**', route => route.fulfill({ status: 404 }));
  await page.goto('/');
  await expect(page.locator('.model-card')).toHaveCount(4);
  await expect(page.locator('.portrait img')).toHaveAttribute('src', /\/assets\/human-.*\.png$/);
  await expect(page.getByRole('button', { name: 'Pending model', exact: true })).toContainText('ダウンロード中');
  await expect(page.getByRole('button', { name: 'Broken model', exact: true })).toContainText('読み込めないモデル');
});
