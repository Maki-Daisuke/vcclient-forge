import { expect, test, type Page } from '@playwright/test';
import { mockSession } from './session-fixtures';

async function openUpload(page: Page) {
  await page.getByRole('button', { name: 'アップロード', exact: true }).first().click();
  return page.getByRole('dialog', { name: 'モデルアップロード' });
}

test('uploads model and optional index in chunks and reloads the model list', async ({ page }) => {
  const state = await mockSession(page);
  const chunks: string[] = [];
  const concats: string[] = [];
  const requests: Record<string, unknown>[] = [];
  await page.route('**/api/uploader/upload_file_chunk', async route => {
    chunks.push(route.request().postDataBuffer()!.toString('latin1'));
    await route.fulfill({ json: { uploaded_filename: 'chunk' } });
  });
  await page.route('**/api/uploader/concat_uploaded_file_chunk', async route => {
    concats.push(route.request().postDataBuffer()!.toString('latin1'));
    await route.fulfill({ json: { generated_filename: 'file' } });
  });
  await page.route('**/api/slot-manager/slots', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    const payload = route.request().postDataJSON();
    requests.push(payload);
    state.models.push({ ...state.models[2], slot_index: 3, name: payload.name });
    await route.fulfill({ json: null });
  });
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.PTH', mimeType: 'application/octet-stream', buffer: Buffer.alloc(4 * 1024 * 1024 + 1, 42) });
  await dialog.getByLabel('インデックスファイルを選択 (任意)').setInputFiles({ name: 'voice.index', mimeType: 'application/octet-stream', buffer: Buffer.from('index') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await expect(dialog.getByRole('status')).toHaveText('モデルを追加しました。');
  expect(chunks).toHaveLength(3);
  expect(concats).toHaveLength(2);
  expect(requests).toHaveLength(1);
  expect(requests[0]).toMatchObject({ voice_changer_type: 'RVC', slot_index: null, name: 'voice' });
  expect(requests[0].model_file).toMatch(/^[a-f0-9-]+\.pth$/);
  expect(requests[0].index_file).toMatch(/^[a-f0-9-]+\.index$/);
  await dialog.getByRole('button', { name: '閉じる', exact: true }).last().click();
  await expect(page.getByRole('button', { name: 'voice', exact: true })).toBeVisible();
});

test('stops before registration when chunk upload fails', async ({ page }) => {
  await mockSession(page);
  let registrations = 0;
  await page.route('**/api/uploader/upload_file_chunk', route => route.fulfill({ status: 503, json: { detail: 'upload failed' } }));
  await page.route('**/api/slot-manager/slots', route => {
    if (route.request().method() !== 'POST') return route.fallback();
    registrations++;
    return route.fulfill({ json: null });
  });
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('HTTP 503');
  expect(registrations).toBe(0);
});

test('requires the user to check the list after a lost registration response', async ({ page }) => {
  await mockSession(page);
  await page.route('**/api/uploader/**', route => route.fulfill({ json: route.request().url().includes('concat_') ? { generated_filename: 'file' } : { uploaded_filename: 'chunk' } }));
  await page.route('**/api/slot-manager/slots', route => route.request().method() === 'POST' ? route.abort() : route.fallback());
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('追加されたか確認できません');
  await expect(dialog.getByRole('button', { name: 'アップロード', exact: true })).toHaveCount(0);
});

test('does not allow upload while native audio is running', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'アップロード', exact: true }).first()).toBeDisabled();
});

test('blocks start and changes while registration is running', async ({ page }) => {
  await mockSession(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/uploader/**', route => route.fulfill({ json: route.request().url().includes('concat_') ? { generated_filename: 'file' } : { uploaded_filename: 'chunk' } }));
  await page.route('**/api/slot-manager/slots', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    await gate;
    await route.fulfill({ json: null });
  });
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await expect(dialog.getByRole('status')).toContainText('登録しています');
  await expect(dialog.getByLabel('モデルファイルを選択')).toBeDisabled();
  await dialog.getByRole('button', { name: '閉じる', exact: true }).last().click();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveAttribute('aria-disabled', 'true');
  await expect(page.getByRole('button', { name: '再読み込み', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('button', { name: '再読み込み', exact: true })).toBeEnabled();
});
