import { expect, test, type Page } from '@playwright/test';
import { ZipWriter, Uint8ArrayWriter, TextReader } from '@zip.js/zip.js';
import { mockSession } from './session-fixtures';

async function makeZip(files: Record<string, string>) {
  const writer = new ZipWriter(new Uint8ArrayWriter());
  for (const [name, content] of Object.entries(files)) await writer.add(name, new TextReader(content));
  return Buffer.from(await writer.close());
}

async function openUpload(page: Page) {
  await page.getByRole('button', { name: 'アップロード', exact: true }).first().click();
  return page.getByRole('dialog', { name: 'モデルアップロード' });
}

test('drops a ZIP, extracts model and index, and imports their bytes', async ({ page }) => {
  const state = await mockSession(page);
  const bodies: string[] = [];
  const submissions: Record<string, unknown>[] = [];
  await page.route('**/api/uploader/**', async route => {
    if (route.request().url().includes('upload_file_chunk')) bodies.push(route.request().postDataBuffer()!.toString('latin1'));
    await route.fulfill({ json: route.request().url().includes('concat_') ? { generated_filename: 'file' } : { uploaded_filename: 'chunk' } });
  });
  await page.route('**/api/slot-manager/slots', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    const payload = route.request().postDataJSON();
    submissions.push(payload);
    state.models.push({ ...state.models[2], slot_index: 3, name: payload.name });
    await route.fulfill({ json: null });
  });
  const zip = await makeZip({ 'folder/voice.pth': 'model bytes', 'folder/voice.index': 'index bytes', 'README.txt': 'info' });
  await page.goto('/');
  const dialog = await openUpload(page);
  const drop = dialog.getByRole('region', { name: 'ZIPをここにドロップ、またはZIPファイルを選択' });
  await drop.evaluate((element, data) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([new Uint8Array(data)], 'voice.zip', { type: 'application/zip' }));
    element.dispatchEvent(new DragEvent('drop', { dataTransfer: transfer, bubbles: true, cancelable: true }));
  }, Array.from(zip));
  await expect(dialog.getByLabel('ZIP内のモデル')).toHaveValue('0');
  await expect(dialog.getByLabel('ZIP内のIndex')).toHaveValue('1');
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await expect(dialog.getByRole('status')).toHaveText('モデルを追加しました。');
  expect(bodies.some(body => body.includes('model bytes'))).toBe(true);
  expect(bodies.some(body => body.includes('index bytes'))).toBe(true);
  expect(submissions[0]).toMatchObject({ name: 'voice', voice_changer_type: 'RVC' });
});

test('asks for model selection when a ZIP contains multiple models', async ({ page }) => {
  await mockSession(page);
  const zip = await makeZip({ 'a.onnx': 'a', 'b.pth': 'b', 'a.index': 'a index', 'b.index': 'b index' });
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.locator('input[accept=".zip"]').setInputFiles({ name: 'models.zip', mimeType: 'application/zip', buffer: zip });
  const submit = dialog.getByRole('button', { name: 'アップロード', exact: true });
  await expect(dialog.getByLabel('ZIP内のモデル')).toHaveValue('');
  await expect(submit).toBeDisabled();
  await dialog.getByLabel('ZIP内のモデル').selectOption({ label: 'b.pth' });
  await dialog.getByLabel('ZIP内のIndex').selectOption({ label: 'b.index' });
  await expect(submit).toBeEnabled();
});

test('reports ZIP files without a model and malformed ZIPs', async ({ page }) => {
  await mockSession(page);
  await page.goto('/');
  const dialog = await openUpload(page);
  const input = dialog.locator('input[accept=".zip"]');
  await input.setInputFiles({ name: 'empty.zip', mimeType: 'application/zip', buffer: await makeZip({ 'readme.txt': 'hi' }) });
  await expect(dialog.getByRole('alert')).toContainText('モデルが見つかりません');
  await input.setInputFiles({ name: 'bad.zip', mimeType: 'application/zip', buffer: Buffer.from('not a zip') });
  await expect(dialog.getByRole('alert')).toContainText('読み込めませんでした');
  await expect(dialog.getByRole('button', { name: 'アップロード', exact: true })).toBeDisabled();
});
