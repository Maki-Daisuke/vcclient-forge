import { test, expect, type Page } from './test-fixtures';
import { mockSession } from './session-fixtures';

async function openEditor(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: '編集', exact: true }).click();
  return page.getByRole('dialog', { name: 'モデル情報の編集' });
}

test('saves a changed name with the latest model fields', async ({ page }) => {
  const state = await mockSession(page);
  const editor = await openEditor(page);
  await expect(editor.getByRole('button', { name: '保存' })).toBeDisabled();
  state.models[0].future_setting = { keep: true };
  await editor.getByLabel('名前', { exact: true }).fill('新しい名前');
  await editor.getByRole('button', { name: '保存' }).click();
  await expect(editor).toHaveCount(0);
  expect(state.modelWrites).toHaveLength(1);
  expect(state.modelWrites[0].data).toMatchObject({ name: '新しい名前', future_setting: { keep: true }, slot_index: 7 });
  await expect(page.getByRole('heading', { name: '8. 新しい名前' })).toBeVisible();
});

test('cancels unsaved changes', async ({ page }) => {
  const state = await mockSession(page);
  const editor = await openEditor(page);
  await editor.getByLabel('名前', { exact: true }).fill('破棄する名前');
  await editor.getByRole('button', { name: 'キャンセル', exact: true }).click();
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await expect(editor.getByLabel('名前', { exact: true })).toHaveValue('Test model B');
  expect(state.modelWrites).toHaveLength(0);
});

test('previews the selected icon and clears the preview on cancel', async ({ page }) => {
  await mockSession(page);
  const editor = await openEditor(page);
  const image = editor.getByRole('img', { name: '新しいアイコン' });
  await expect(image).toHaveCount(0);
  const pixel = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+lmz8AAAAASUVORK5CYII=', 'base64');
  await editor.getByLabel('アイコンを選択').setInputFiles({ name: 'icon.png', mimeType: 'image/png', buffer: pixel });
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute('src', /^blob:/);
  await editor.getByRole('button', { name: 'キャンセル', exact: true }).click();
  await page.getByRole('button', { name: '編集', exact: true }).click();
  await expect(image).toHaveCount(0);
});

test('uploads an icon before saving the name without overwriting the new icon', async ({ page }) => {
  const state = await mockSession(page);
  let uploaded = '';
  await page.route('**/api/uploader/**', async route => {
    const form = route.request().postDataBuffer()!.toString('latin1');
    const match = form.match(/[0-9a-f-]{36}\.png/i);
    if (match) uploaded = match[0];
    await route.fulfill({ json: route.request().url().includes('concat_') ? { generated_filename: uploaded } : { uploaded_filename: uploaded } });
  });
  await page.route('**/api/slot-manager/slots/operation/set_icon_file', async route => {
    const body = route.request().postDataJSON();
    expect(body).toEqual({ slot_index: 7, icon_file: uploaded });
    state.models[0].icon_file = uploaded;
    await route.fulfill({ json: null });
  });
  const editor = await openEditor(page);
  await editor.getByLabel('名前', { exact: true }).fill('新しい名前');
  await editor.getByLabel('アイコンを選択').setInputFiles({ name: 'icon.png', mimeType: 'image/png', buffer: Buffer.from('image') });
  await editor.getByRole('button', { name: '保存' }).click();
  await expect(editor).toHaveCount(0);
  expect(state.modelWrites[0].data).toMatchObject({ name: '新しい名前', icon_file: uploaded });
  await expect(page.locator('.portrait img')).toHaveAttribute('src', `/model_dir/7/${uploaded}`);
});

test('keeps the draft and reports a partial save when the name update fails', async ({ page }) => {
  const state = await mockSession(page);
  state.modelStatus = 500;
  await page.route('**/api/uploader/**', route => route.fulfill({ json: route.request().url().includes('concat_') ? { generated_filename: 'file' } : { uploaded_filename: 'chunk' } }));
  await page.route('**/api/slot-manager/slots/operation/set_icon_file', async route => {
    state.models[0].icon_file = route.request().postDataJSON().icon_file;
    await route.fulfill({ json: null });
  });
  const editor = await openEditor(page);
  await editor.getByLabel('名前', { exact: true }).fill('未保存の名前');
  await editor.getByLabel('アイコンを選択').setInputFiles({ name: 'icon.png', mimeType: 'image/png', buffer: Buffer.from('image') });
  await editor.getByRole('button', { name: '保存' }).click();
  await expect(editor.getByRole('alert')).toContainText('一部は保存されている可能性');
  await expect(editor.getByLabel('名前', { exact: true })).toHaveValue('未保存の名前');
  expect(state.models[0].name).toBe('Test model B');
  expect(state.models[0].icon_file).toMatch(/\.png$/);
});

test('does not allow editing while conversion is running', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const editor = await openEditor(page);
  await expect(editor.getByLabel('名前', { exact: true })).toBeDisabled();
  await expect(editor.getByLabel('アイコンを選択')).toBeDisabled();
  await expect(editor.getByText('モデル情報を編集するには、先に音声変換を停止してください。')).toBeVisible();
});

test('keeps the dialog open while saving', async ({ page }) => {
  const state = await mockSession(page);
  let release!: () => void;
  state.modelGate = new Promise<void>(resolve => { release = resolve; });
  const editor = await openEditor(page);
  await editor.getByLabel('名前', { exact: true }).fill('保存中の名前');
  await editor.getByRole('button', { name: '保存' }).click();
  await expect(editor.getByRole('status')).toHaveText('モデル情報を保存しています…');
  await expect(editor.getByRole('button', { name: 'キャンセル' })).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(editor).toBeVisible();
  release();
  await expect(editor).toHaveCount(0);
});
