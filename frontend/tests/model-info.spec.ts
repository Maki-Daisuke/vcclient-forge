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
  expect(state.modelWrites[0].data).toEqual({ name: '新しい名前' });
  expect(state.models.find(model => model.slot_index === 7)).toMatchObject({ name: '新しい名前', future_setting: { keep: true }, slot_index: 7 });
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

test('uploads icon and name together in one PATCH request', async ({ page }) => {
  const state = await mockSession(page);
  const editor = await openEditor(page);
  await editor.getByLabel('名前', { exact: true }).fill('新しい名前');
  await editor.getByLabel('アイコンを選択').setInputFiles({ name: 'icon.png', mimeType: 'image/png', buffer: Buffer.from('image') });
  await editor.getByRole('button', { name: '保存' }).click();
  await expect(editor).toHaveCount(0);
  expect(state.modelWrites).toHaveLength(1);
  expect(state.modelWrites[0].data).toMatchObject({ name: '新しい名前' });
  expect(state.modelWrites[0].data.icon_file).toMatch(/^icon_1_icon\.png$/);
  await expect(page.locator('.portrait img')).toHaveAttribute('src', `/model_dir/7/${state.modelWrites[0].data.icon_file}`);
});

test('keeps the draft and leaves saved model unchanged when atomic PATCH fails', async ({ page }) => {
  const state = await mockSession(page);
  const beforeIcon = state.models[0].icon_file;
  state.modelStatus = 500;
  const editor = await openEditor(page);
  await editor.getByLabel('名前', { exact: true }).fill('未保存の名前');
  await editor.getByLabel('アイコンを選択').setInputFiles({ name: 'icon.png', mimeType: 'image/png', buffer: Buffer.from('image') });
  await editor.getByRole('button', { name: '保存' }).click();
  await expect(editor.getByRole('alert')).toContainText('モデル情報を保存できませんでした');
  await expect(editor.getByLabel('名前', { exact: true })).toHaveValue('未保存の名前');
  expect(state.models[0].name).toBe('Test model B');
  expect(state.models[0].icon_file).toBe(beforeIcon);
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
