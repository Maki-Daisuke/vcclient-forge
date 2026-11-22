import { expect, test, type Page } from './test-fixtures';
import { ZipWriter, Uint8ArrayWriter, TextReader } from '@zip.js/zip.js';
import { mockSession, readMultipart } from './session-fixtures';

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
  const submissions: { name: FormDataEntryValue | null; modelBytes: string; indexBytes: string | null }[] = [];
  await page.route('**/api/models', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    const form = await readMultipart(route.request());
    const modelFile = form.get('model_file') as File;
    const indexFile = form.get('index_file');
    const name = String(form.get('name'));
    submissions.push({
      name: form.get('name'),
      modelBytes: await modelFile.text(),
      indexBytes: indexFile instanceof File ? await indexFile.text() : null,
    });
    const created = { ...state.models[0], id: 'model_c', name };
    state.models.push(created);
    await route.fulfill({ status: 201, json: created });
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
  expect(submissions).toEqual([{
    name: 'voice',
    modelBytes: 'model bytes',
    indexBytes: 'index bytes',
  }]);
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
