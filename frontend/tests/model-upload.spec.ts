import { expect, test, type Page } from './test-fixtures';
import { openControlSections } from './catalog-fixtures';
import { mockSession, readMultipart } from './session-fixtures';

async function trackMultipartUpload(page: Page) {
  await page.addInitScript(() => {
    const NativeXHR = window.XMLHttpRequest;
    const uploads: XMLHttpRequestUpload[] = [];
    (window as unknown as { __emitUploadProgress?: (loaded: number, total: number) => void }).__emitUploadProgress = (loaded, total) => {
      for (const upload of uploads) {
        upload.dispatchEvent(new ProgressEvent('progress', { lengthComputable: true, loaded, total }));
        if (loaded >= total) upload.dispatchEvent(new ProgressEvent('load'));
      }
    };
    window.XMLHttpRequest = class extends NativeXHR {
      open(method: string, url: string | URL, ...rest: unknown[]) {
        if (method === 'POST' && String(url) === '/api/models') uploads.push(this.upload);
        return super.open(method, url, ...(rest as [boolean, string?, string?]));
      }
    } as typeof XMLHttpRequest;
  });
  return (loaded: number, total = 4) => page.evaluate(
    ([l, t]) => (window as unknown as { __emitUploadProgress: (loaded: number, total: number) => void }).__emitUploadProgress(l, t),
    [loaded, total] as const,
  );
}

async function pauseSlotPost(page: Page, finish: (route: import('@playwright/test').Route) => Promise<void>) {
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let markIntercepted!: () => void;
  const intercepted = new Promise<void>(resolve => { markIntercepted = resolve; });
  await page.route('**/api/models', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    markIntercepted();
    await gate;
    await finish(route);
  });
  return { intercepted, release };
}

async function openUpload(page: Page) {
  await page.getByRole('button', { name: 'アップロード', exact: true }).first().click();
  return page.getByRole('dialog', { name: 'モデルアップロード' });
}

test('uploads model and optional index in one multipart request and reloads the model list', async ({ page }) => {
  const state = await mockSession(page);
  const requests: { name: FormDataEntryValue | null; modelName: string; modelSize: number; indexName: string | null; indexBytes: string | null }[] = [];
  await page.route('**/api/models', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    const form = await readMultipart(route.request());
    const modelFile = form.get('model_file') as File;
    const indexFile = form.get('index_file');
    const name = String(form.get('name'));
    requests.push({
      name: form.get('name'),
      modelName: modelFile.name,
      modelSize: modelFile.size,
      indexName: indexFile instanceof File ? indexFile.name : null,
      indexBytes: indexFile instanceof File ? await indexFile.text() : null,
    });
    const created = { ...state.models[0], id: 'model_c', name };
    state.models.push(created);
    await route.fulfill({ status: 201, json: created });
  });
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.PTH', mimeType: 'application/octet-stream', buffer: Buffer.alloc(4 * 1024 * 1024 + 1, 42) });
  await dialog.getByLabel('インデックスファイルを選択 (任意)').setInputFiles({ name: 'voice.index', mimeType: 'application/octet-stream', buffer: Buffer.from('index') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await expect(dialog.getByRole('status')).toHaveText('モデルを追加しました。');
  expect(requests).toEqual([{
    name: 'voice',
    modelName: 'voice.PTH',
    modelSize: 4 * 1024 * 1024 + 1,
    indexName: 'voice.index',
    indexBytes: 'index',
  }]);
  await dialog.getByRole('button', { name: '閉じる', exact: true }).last().click();
  await expect(page.getByRole('button', { name: 'voice', exact: true })).toBeVisible();
});

test('reports HTTP error when multipart upload fails', async ({ page }) => {
  await mockSession(page);
  await page.route('**/api/models', route => {
    if (route.request().method() !== 'POST') return route.fallback();
    return route.fulfill({ status: 503, json: { code: 'internal_error', message: 'upload failed' } });
  });
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await expect(dialog.getByRole('alert')).toContainText('HTTP 503');
});

test('requires the user to check the list after a lost registration response', async ({ page }) => {
  const emitProgress = await trackMultipartUpload(page);
  await mockSession(page);
  const { intercepted, release } = await pauseSlotPost(page, route => route.abort());
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await intercepted;
  await emitProgress(4, 4);
  await expect(dialog.getByRole('status')).toContainText('登録しています');
  release();
  await expect(dialog.getByRole('alert')).toContainText('追加されたか確認できません');
  await expect(dialog.getByRole('button', { name: 'アップロード', exact: true })).toHaveCount(0);
});

test('reports an upload error instead of uncertain when connection drops mid-upload', async ({ page }) => {
  const emitProgress = await trackMultipartUpload(page);
  await mockSession(page);
  const { intercepted, release } = await pauseSlotPost(page, route => route.abort());
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await intercepted;
  await emitProgress(2, 4);
  await expect(dialog.getByRole('status')).toContainText('50%');
  release();
  await expect(dialog.getByRole('alert')).not.toContainText('追加されたか確認できません');
  await expect(dialog.getByRole('button', { name: 'アップロード', exact: true })).toBeEnabled();
});

test('allows uploading a model while native audio is running', async ({ page }) => {
  const emitProgress = await trackMultipartUpload(page);
  const state = await mockSession(page);
  state.active = true;
  const { intercepted, release } = await pauseSlotPost(page, async route => {
    const form = await readMultipart(route.request());
    const created = { ...state.models[0], id: 'model_c', name: String(form.get('name')) };
    state.models.push(created);
    await route.fulfill({ status: 201, json: created });
  });
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('button', { name: 'アップロード', exact: true }).first()).toBeEnabled();
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await intercepted;
  await emitProgress(4, 4);
  await expect(dialog.getByRole('status')).toContainText('登録しています');
  await dialog.getByRole('button', { name: '閉じる', exact: true }).last().click();

  await expect(page.getByRole('button', { name: 'パススルー' })).toBeEnabled();
  await expect(page.getByRole('button', { name: '録音', exact: true })).toBeEnabled();
  const inputGain = page.getByRole('slider', { name: '入力音量', exact: true });
  await expect(inputGain).toBeEnabled();
  await inputGain.press('ArrowRight');
  await expect.poll(() => state.sessionWrites.length).toBe(1);
  expect(state.sessionWrites[0].input_gain).toBe(2.71);

  release();
  await expect(page.getByRole('button', { name: 'voice', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
});

test('blocks start and changes while registration is running', async ({ page }) => {
  const emitProgress = await trackMultipartUpload(page);
  const state = await mockSession(page);
  const { intercepted, release } = await pauseSlotPost(page, route => route.fulfill({ json: state.models[2] }));
  await page.goto('/');
  const dialog = await openUpload(page);
  await dialog.getByLabel('モデルファイルを選択').setInputFiles({ name: 'voice.onnx', mimeType: 'application/octet-stream', buffer: Buffer.from('data') });
  await dialog.getByRole('button', { name: 'アップロード', exact: true }).click();
  await intercepted;
  await emitProgress(4, 4);
  await expect(dialog.getByRole('status')).toContainText('登録しています');
  await expect(dialog.getByLabel('モデルファイルを選択')).toBeDisabled();
  await dialog.getByRole('button', { name: '閉じる', exact: true }).last().click();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toHaveAttribute('aria-disabled', 'true');
  await expect(page.getByRole('button', { name: '再読み込み', exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole('button', { name: '再読み込み', exact: true })).toBeEnabled();
});
