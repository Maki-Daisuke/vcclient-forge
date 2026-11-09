import { test, expect } from '@playwright/test';
import { configuration, fulfillCatalog, slots } from './catalog-fixtures';

test('deletes the selected model after confirmation and clears the selection', async ({ page }) => {
  let deleted = false;
  let body: unknown;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/slot-manager/operation/organize') {
      body = route.request().postDataJSON();
      deleted = true;
      await route.fulfill({ json: { current_slot_index: -1 } });
    } else if (deleted && path === '/api/slot-manager/slots') {
      await route.fulfill({ json: [{ ...slots[2], slot_index: 0 }] });
    } else if (deleted && path === '/api/configuration-manager/configuration') {
      await route.fulfill({ json: { ...configuration, current_slot_index: -1 } });
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
  expect(body).toEqual({ order: [2], delete_selected: true });
  await expect(page.getByRole('heading', { name: /Test model B/ })).toHaveCount(0);
});

test('explains why deleting is unavailable during conversion', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (new URL(route.request().url()).pathname === '/api/local-voice-changer-interface/information') {
      await route.fulfill({ json: { local_voice_changer_interface_active: true } });
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
    if (path === '/api/slot-manager/operation/organize') {
      body = route.request().postDataJSON();
      saved = true;
      await route.fulfill({ json: { current_slot_index: 0 } });
    } else if (saved && path === '/api/slot-manager/slots') {
      await route.fulfill({ json: [{ ...slots[0], slot_index: 0 }, { ...slots[2], slot_index: 1 }] });
    } else if (saved && path === '/api/configuration-manager/configuration') {
      await route.fulfill({ json: { ...configuration, current_slot_index: 0 } });
    } else await fulfillCatalog(route);
  });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'モデル管理' })).toHaveCount(0);
  await page.getByRole('button', { name: '並べ替え', exact: true }).click();
  await expect(page.locator('.reorder-hint')).toHaveText('ドラッグ＆ドロップで並び替えたら確定を押してください');
  await page.getByRole('group', { name: 'Test model B' }).dragTo(page.getByRole('group', { name: 'Test model A' }));
  await page.getByRole('button', { name: '確定', exact: true }).click();
  await expect.poll(() => body).toEqual({ order: [7, 2], delete_selected: false });
  await expect(page.locator('.model-cards .model-name')).toHaveText(['Test model B', 'Test model A']);
  await expect(page.getByRole('heading', { name: '1. Test model B' })).toBeVisible();
  await expect(page.locator('.reorder-hint')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '再読み込み' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'アップロード', exact: true })).toBeEnabled();
});

test('explains when the running backend needs a restart', async ({ page }) => {
  await page.route('**/api/**', async route => {
    if (new URL(route.request().url()).pathname === '/api/slot-manager/operation/organize') {
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
