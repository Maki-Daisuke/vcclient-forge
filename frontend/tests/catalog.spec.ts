import { test, expect } from './test-fixtures';
import { slots, fulfillCatalog, mockCatalog } from './catalog-fixtures';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/models/*/icon**', route => route.fulfill({ status: 404 }));
});

test('renders models, metadata, and the selected portrait using catalog IDs', async ({ page }) => {
  await mockCatalog(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'モデル選択', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '2. Test model B' })).toBeVisible();
  await expect(page.locator('.model-card')).toHaveCount(2);
  await expect(page.locator('.model-name')).toHaveText(['Test model A', 'Test model B']);
  await expect(page.locator('.model-card[aria-current=true]')).toHaveAccessibleName('Test model B');
  await expect(page.locator('.models-panel')).not.toContainText('Description of the selected model');
  await expect(page.locator('.tags')).toContainText('onnx v1');
  await expect(page.locator('.tags')).toContainText('non-f0');
  await expect(page.locator('.portrait img')).toHaveAttribute('src', '/api/models/model_b/icon?v=1');
  await expect(page.locator('.models-panel .count')).toHaveCount(0);
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('textbox', { name: '名前', exact: true })).toHaveValue('Test model B');
  await expect(page.getByRole('dialog').getByRole('textbox', { name: '説明', exact: true })).toHaveCount(0);
});

test('shows loading until both the model list and the selection arrive', async ({ page }) => {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/**', async route => {
    if (route.request().url().endsWith('/settings')) await pending;
    await fulfillCatalog(route);
  });
  await page.goto('/');
  await expect(page.locator('.models-panel .catalog-message[role=status]')).toContainText('モデル情報を読み込んでいます');
  await expect(page.locator('.model-card')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '再読み込み', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('heading', { name: '2. Test model B' })).toBeVisible();
});

test('empty catalog shows an empty state with no fake models', async ({ page }) => {
  await page.route('**/api/**', route => fulfillCatalog(route, [], null));
  await page.goto('/');
  await expect(page.locator('.models-panel .catalog-message[role=status]')).toHaveText('保存されているモデルはありません。モデルをアップロードしてください。');
  await expect(page.locator('.model-card')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'モデルが選択されていません' })).toBeVisible();
  await expect(page.getByRole('button', { name: '編集', exact: true })).toBeDisabled();
  await expect(page.locator('.portrait img')).toHaveCount(0);
  await expect(page.locator('.model-message')).toHaveCount(0);
});

test('a missing selected model does not select the first model', async ({ page }) => {
  await page.route('**/api/**', route => fulfillCatalog(route, slots, 'missing_id'));
  await page.goto('/');
  await expect(page.locator('.model-message')).toContainText('ID: missing_id');
  await expect(page.locator('.model-card')).toHaveCount(2);
  await expect(page.locator('.model-card[aria-current=true]')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '編集', exact: true })).toBeDisabled();
});

test('network failure clears old models and reload recovers the current selection', async ({ page }) => {
  let online = true;
  let selectedId = 'model_b';
  await page.route('**/api/**', route => online ? fulfillCatalog(route, slots, selectedId) : route.abort('connectionrefused'));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '2. Test model B' })).toBeVisible();
  online = false;
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('バックエンドに接続できません');
  await expect(page.locator('.model-card')).toHaveCount(0);
  await expect(page.locator('.model-message')).toHaveCount(0);
  await expect(page.locator('.portrait img')).toHaveCount(0);
  online = true;
  selectedId = 'model_a';
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.getByRole('heading', { name: '1. Test model A' })).toBeVisible();
  await expect(page.locator('.models-panel').getByRole('alert')).toHaveCount(0);
});

test('reloads /api/models on manual reload', async ({ page }) => {
  let calls = 0;
  let currentModels: Record<string, unknown>[] = slots;
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/models') {
      calls++;
      return route.fulfill({ json: currentModels });
    }
    return fulfillCatalog(route);
  });
  await page.goto('/');
  await expect(page.locator('.model-card')).toHaveCount(2);
  expect(calls).toBe(1);
  currentModels = [...slots, { ...slots[0], id: 'model_c', name: 'Test model C' }];
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Test model C', exact: true })).toBeVisible();
  expect(calls).toBe(2);
});

for (const invalid of [
  { name: 'HTML in place of JSON', response: { contentType: 'text/html', body: '<html>wrong server</html>' } },
  { name: 'an unexpected list envelope', response: { json: { models: slots } } },
  { name: 'a nonstring ID', response: { json: [{ ...slots[0], id: 7 }] } },
  { name: 'duplicate IDs', response: { json: [slots[0], slots[0]] } },
]) {
  test(`rejects ${invalid.name}`, async ({ page }) => {
    await page.route('**/api/**', route => new URL(route.request().url()).pathname === '/api/models'
      ? route.fulfill(invalid.response) : fulfillCatalog(route));
    await page.goto('/');
    await expect(page.locator('.models-panel').getByRole('alert')).toContainText('応答形式が想定と異なる');
    await expect(page.locator('.model-card')).toHaveCount(0);
  });
}

test('a failed configuration request does not publish a partial list', async ({ page }) => {
  await page.route('**/api/**', route => route.request().url().endsWith('/settings')
    ? route.fulfill({ status: 503 }) : fulfillCatalog(route));
  await page.goto('/');
  await expect(page.locator('.models-panel').getByRole('alert')).toContainText('HTTP 503');
  await expect(page.locator('.model-card')).toHaveCount(0);
});

test('an invalid current model ID does not silently choose a model', async ({ page }) => {
  await page.route('**/api/**', route => route.request().url().endsWith('/settings')
    ? route.fulfill({ json: { model_id: 7 } }) : fulfillCatalog(route));
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
  await expect(page.getByRole('heading', { name: '2. Test model B' })).toBeVisible();
});

test('broken images use a placeholder', async ({ page }) => {
  await page.route('**/api/**', route => fulfillCatalog(route, slots));
  await page.route('**/api/models/*/icon**', route => route.fulfill({ status: 404 }));
  await page.goto('/');
  await expect(page.locator('.model-card')).toHaveCount(2);
  await expect(page.locator('.portrait img')).toHaveAttribute('src', /\/assets\/human-.*\.png$/);
});
