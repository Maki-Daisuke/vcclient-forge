import { test, expect } from './test-fixtures';
import { configuration, fulfillCatalog, mockModelImages, slots } from './catalog-fixtures';

test.beforeEach(async ({ page }) => { await mockModelImages(page); });

test('deletes the selected model after confirmation and clears the selection', async ({ page }) => {
  let deleted = false;
  let body: unknown;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/models/model_b' && route.request().method() === 'DELETE') {
      body = { method: route.request().method(), path };
      deleted = true;
      await route.fulfill({ status: 204 });
    } else if (deleted && path === '/api/models') {
      await route.fulfill({ json: [slots[0]] });
    } else if (deleted && path === '/api/settings') {
      await route.fulfill({ json: { ...configuration, model_id: null } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  const editDialog = page.getByRole('dialog', { name: 'モデル情報の編集' });
  await expect(editDialog).toBeVisible();
  await expect(editDialog.getByRole('button', { name: '閉じる' })).toHaveCount(0);
  await expect(editDialog.getByRole('button', { name: 'キャンセル' })).toBeVisible();
  await page.getByRole('button', { name: 'モデルを削除' }).click();
  const confirmation = page.getByRole('dialog', { name: 'このモデルを削除しますか？' });
  await expect(confirmation).toBeVisible();
  const outerBox = await page.locator('.dialog-content').first().boundingBox();
  const innerBox = await confirmation.boundingBox();
  const descriptionBox = await confirmation.getByText('モデルのファイルが削除されます。この操作は取り消せません。').boundingBox();
  const deleteButton = confirmation.getByRole('button', { name: '削除', exact: true });
  const cancelButton = confirmation.getByRole('button', { name: 'キャンセル', exact: true });
  const deleteBox = await deleteButton.boundingBox();
  const cancelBox = await cancelButton.boundingBox();
  expect(innerBox!.width).toBeLessThan(outerBox!.width);
  expect(descriptionBox!.x).toBeGreaterThan(innerBox!.x);
  expect(deleteBox!.x).toBeLessThan(cancelBox!.x);
  await deleteButton.click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(body).toEqual({ method: 'DELETE', path: '/api/models/model_b' });
  await expect(page.getByRole('heading', { name: /Test model B/ })).toHaveCount(0);
});

test('deletes consecutive models without starting conversion', async ({ page }) => {
  let models = [{ ...slots[0] }, { ...slots[1] }];
  let selected: string | null = 'model_b';
  const deleted: string[] = [];
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const match = path.match(/^\/api\/models\/([^/]+)$/);
    if (match && route.request().method() === 'DELETE') {
      const id = decodeURIComponent(match[1]);
      deleted.push(id);
      models = models.filter(model => model.id !== id);
      selected = null;
      await route.fulfill({ status: 204 });
    } else if (path === '/api/models') {
      await route.fulfill({ json: models });
    } else if (path === '/api/settings') {
      await route.fulfill({ json: { ...configuration, model_id: selected } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await page.getByRole('button', { name: 'モデルを削除' }).click();
  await page.getByRole('dialog', { name: 'このモデルを削除しますか？' }).getByRole('button', { name: '削除', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Test model A', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Test model A', exact: true }).click();
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await expect(page.getByRole('button', { name: 'モデルを削除' })).not.toHaveAttribute('aria-disabled', 'true');
  await page.getByRole('button', { name: 'モデルを削除' }).click();
  await page.getByRole('dialog', { name: 'このモデルを削除しますか？' }).getByRole('button', { name: '削除', exact: true }).click();
  await expect.poll(() => deleted).toEqual(['model_b', 'model_a']);
});

test('reloads models and configuration after a failed deletion', async ({ page }) => {
  let failed = false;
  let reloadedSlots = false;
  let reloadedConfiguration = false;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/models/model_b' && route.request().method() === 'DELETE') {
      failed = true;
      await route.fulfill({ status: 500, json: { code: 'internal_error', message: 'Delete failed' } });
    } else {
      if (failed && path === '/api/models') reloadedSlots = true;
      if (failed && path === '/api/settings') reloadedConfiguration = true;
      await fulfillCatalog(route);
    }
  });
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await page.getByRole('button', { name: 'モデルを削除' }).click();
  await page.getByRole('dialog', { name: 'このモデルを削除しますか？' }).getByRole('button', { name: '削除', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Delete failed');
  await expect.poll(() => reloadedSlots && reloadedConfiguration).toBe(true);
  await expect(page.getByRole('button', { name: 'Test model B', exact: true })).toBeVisible();
});

test('does not report a missing model 404 as needing a backend restart', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/models/model_b' && route.request().method() === 'DELETE') {
      await route.fulfill({
        status: 404,
        json: { code: 'model_not_found', message: 'Model does not exist' },
      });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await page.getByRole('button', { name: 'モデルを削除' }).click();
  await page.getByRole('dialog', { name: 'このモデルを削除しますか？' }).getByRole('button', { name: '削除', exact: true }).click();
  const alert = page.getByRole('alert');
  await expect(alert).toContainText('Model does not exist');
  await expect(alert).not.toContainText('バックエンドを再起動');
});

test('explains when deleting requires restarting an older backend returning 405', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/models/model_b' && route.request().method() === 'DELETE') {
      await route.fulfill({ status: 405, json: { detail: 'Method Not Allowed' } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await page.getByRole('button', { name: 'モデルを削除' }).click();
  await page.getByRole('dialog', { name: 'このモデルを削除しますか？' }).getByRole('button', { name: '削除', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('バックエンドを再起動');
});

test('does not show stale reorder errors inside the delete confirmation dialog', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (new URL(route.request().url()).pathname === '/api/models/order') {
      await route.fulfill({ status: 500, json: { code: 'internal_error', message: 'Organize failed' } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await page.getByRole('button', { name: '並べ替え', exact: true }).click();
  await page.getByRole('button', { name: '確定', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Organize failed');
  await page.getByRole('button', { name: 'キャンセル', exact: true }).click();
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await page.getByRole('button', { name: 'モデルを削除' }).click();
  const confirmDialog = page.getByRole('dialog', { name: 'このモデルを削除しますか？' });
  await expect(confirmDialog).toBeVisible();
  await expect(confirmDialog.getByRole('alert')).toHaveCount(0);
});

test('explains why deleting is unavailable during conversion', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (new URL(route.request().url()).pathname === '/api/session') {
      await route.fulfill({
        json: {
          status: 'running',
          snapshot: {
            ...configuration,
            model_id: 'model_b',
            pitch_shift: -5,
            index_ratio: 0.63,
            chunk_sec: 0.3,
            pitch_estimator: 'rmvpe',
            pass_through: false,
            recording: false,
          },
          locked_fields: ['model_id'],
          input_sample_rate: 48000,
          output_sample_rate: 48000,
          monitor_sample_rate: null,
          last_error: null,
        },
      });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  const button = page.getByRole('button', { name: 'モデルを削除' });
  await expect(button).toHaveAttribute('aria-disabled', 'true');
  await button.focus();
  await expect(page.getByRole('tooltip')).toHaveText('削除するには、先に音声変換を停止してください。');
  await button.click({ force: true });
  await expect(page.getByRole('dialog', { name: 'このモデルを削除しますか？' })).toHaveCount(0);
});

test('reorders models with drag and commits the displayed order', async ({ page }) => {
  let body: unknown;
  let saved = false;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/models/order' && route.request().method() === 'PUT') {
      body = route.request().postDataJSON();
      saved = true;
      await route.fulfill({ json: body });
    } else if (saved && path === '/api/models') {
      await route.fulfill({ json: [slots[1], slots[0]] });
    } else if (saved && path === '/api/settings') {
      await route.fulfill({ json: { ...configuration, model_id: 'model_b' } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'モデル管理' })).toHaveCount(0);
  await page.getByRole('button', { name: '並べ替え', exact: true }).click();
  await expect(page.locator('.reorder-hint')).toHaveText('ドラッグ＆ドロップで並び替えたら確定を押してください');
  await page.getByRole('group', { name: 'Test model B' }).dragTo(page.getByRole('group', { name: 'Test model A' }));
  await page.getByRole('button', { name: '確定', exact: true }).click();
  await expect.poll(() => body).toEqual({ model_ids: ['model_b', 'model_a'] });
  await expect(page.locator('.model-cards .model-name')).toHaveText(['Test model B', 'Test model A']);
  await expect(page.getByRole('heading', { name: '1. Test model B' })).toBeVisible();
  await expect(page.locator('.reorder-hint')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '再読み込み' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'アップロード', exact: true })).toBeEnabled();
});

test('explains when the running backend needs a restart', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (new URL(route.request().url()).pathname === '/api/models/order') {
      await route.fulfill({ status: 404, json: { detail: 'Not Found' } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await page.getByRole('button', { name: '並べ替え', exact: true }).click();
  await page.getByRole('button', { name: '確定', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('バックエンドを再起動');
});

test('hides reload and upload while reordering and restores them on cancel', async ({ page }) => {
  await page.route('**/api/**', route => fulfillCatalog(route));
  await page.goto('/');
  await page.getByRole('button', { name: '並べ替え', exact: true }).click();
  await expect(page.getByRole('button', { name: '再読み込み' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'アップロード', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Test model B' }).focus();
  await page.keyboard.press('ArrowLeft');
  await expect(page.locator('.model-cards .model-name')).toHaveText(['Test model A', 'Test model B']);
  await page.getByRole('button', { name: 'キャンセル', exact: true }).click();
  await expect(page.getByRole('button', { name: '再読み込み' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'アップロード', exact: true })).toBeEnabled();
});

test('reorders models while conversion is running', async ({ page }) => {
  let body: unknown;
  let saved = false;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/session') {
      await route.fulfill({
        json: {
          status: 'running',
          snapshot: {
            ...configuration,
            model_id: 'model_b',
            pitch_shift: -5,
            index_ratio: 0.63,
            chunk_sec: 0.3,
            pitch_estimator: 'rmvpe',
            pass_through: false,
            recording: false,
          },
          locked_fields: ['model_id'],
          input_sample_rate: 48000,
          output_sample_rate: 48000,
          monitor_sample_rate: null,
          last_error: null,
        },
      });
    } else if (path === '/api/models/order' && route.request().method() === 'PUT') {
      body = route.request().postDataJSON();
      saved = true;
      await route.fulfill({ json: body });
    } else if (saved && path === '/api/models') {
      await route.fulfill({ json: [slots[1], slots[0]] });
    } else if (saved && path === '/api/settings') {
      await route.fulfill({ json: { ...configuration, model_id: 'model_b' } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '並べ替え', exact: true }).click();
  await page.getByRole('group', { name: 'Test model B' }).dragTo(page.getByRole('group', { name: 'Test model A' }));
  await page.getByRole('button', { name: '確定', exact: true }).click();
  await expect.poll(() => body).toEqual({ model_ids: ['model_b', 'model_a'] });
  await expect(page.locator('.model-cards .model-name')).toHaveText(['Test model B', 'Test model A']);
  await expect(page.getByRole('heading', { name: '1. Test model B' })).toBeVisible();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
});
