import { expect, test, type Page } from '@playwright/test';
import { mockSession } from './session-fixtures';

function wav(dataSize = 4): Buffer {
  const data = Buffer.alloc(44 + dataSize);
  data.write('RIFF', 0); data.writeUInt32LE(36 + dataSize, 4); data.write('WAVEfmt ', 8);
  data.writeUInt32LE(16, 16); data.writeUInt16LE(1, 20); data.writeUInt16LE(1, 22);
  data.writeUInt32LE(48000, 24); data.writeUInt32LE(96000, 28); data.writeUInt16LE(2, 32);
  data.writeUInt16LE(16, 34); data.write('data', 36); data.writeUInt32LE(dataSize, 40);
  return data;
}

async function mockRecording(page: Page, dataSize = 4) {
  await page.route('**/output.wav', route => route.fulfill({ contentType: 'audio/wav', body: wav(dataSize) }));
}

async function mockClientAudio(page: Page) {
  await page.routeWebSocket(/\/socket\.io\//, socket => {
    socket.send('0{"sid":"test","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}');
    socket.onMessage(message => {
      if (typeof message === 'string' && message.startsWith('40/test,')) socket.send('40/test,{"sid":"test"}');
    });
  });
  await page.addInitScript(() => {
    const audio = new AudioContext();
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => audio.createMediaStreamDestination().stream });
  });
}

test('client recording supports passthrough and returns to armed state after stopping', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  state.config.output_sample_rate = 48000;
  state.config.pass_through = true;
  await mockRecording(page);
  await mockClientAudio(page);
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await record.click();
  await expect(record).toContainText('録音待機');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(record).toContainText('録音中');
  await expect.poll(() => state.config.recording_started).toBe(true);
  const passthrough = page.getByRole('button', { name: 'パススルー' });
  await passthrough.click();
  await expect.poll(() => state.config.pass_through).toBe(false);
  await expect(passthrough).toBeEnabled();
  await passthrough.click();
  await expect.poll(() => state.config.pass_through).toBe(true);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '停止', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('output.wav');
  await expect(record).toContainText('録音待機');
  expect(state.config.recording_started).toBe(false);
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(record).toContainText('録音中');
  const nextDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: '停止', exact: true }).click();
  expect((await nextDownload).suggestedFilename()).toBe('output.wav');
  await expect(record).toContainText('録音待機');
});

test('client recording can be started and stopped during conversion', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  state.config.output_sample_rate = 48000;
  await mockRecording(page);
  await mockClientAudio(page);
  await page.goto('/');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  const record = page.getByRole('button', { name: '録音', exact: true });
  await record.click();
  await expect(record).toContainText('録音中');
  await expect.poll(() => state.config.recording_started).toBe(true);
  await expect(record).toBeEnabled();
  const download = page.waitForEvent('download');
  await record.click();
  expect((await download).suggestedFilename()).toBe('output.wav');
  await expect(record).toHaveAttribute('aria-pressed', 'false');
  expect(state.config.recording_started).toBe(false);
});

test('empty recording shows a notice without downloading', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.recording_started = true;
  await mockRecording(page, 0);
  let downloads = 0;
  page.on('download', () => { downloads++; });
  await page.goto('/');
  await expect(page.locator('main > .configuration-status')).toBeHidden();
  await page.getByRole('button', { name: '録音', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '録音された音声がありません。' })).toBeVisible();
  expect(downloads).toBe(0);
  expect(state.config.recording_started).toBe(false);
  await page.locator('main > .configuration-status').getByRole('button', { name: '閉じる' }).click();
  await expect(page.locator('main > .configuration-status')).toBeHidden();
});

test('a failed microphone start clears backend recording while preserving the armed state', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  state.config.output_sample_rate = 48000;
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: () => Promise.reject(new DOMException('Denied', 'NotAllowedError')) });
  });
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await record.click();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('マイクの許可');
  await expect(record).toContainText('録音待機');
  expect(state.writes.map(write => write.recording_started)).toEqual([false, true, false]);
  expect(state.config.recording_started).toBe(false);
});

test('a failed recording download shows a notice instead of opening a download', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.recording_started = true;
  await page.route('**/output.wav', route => route.fulfill({ status: 500 }));
  let downloads = 0;
  page.on('download', () => { downloads++; });
  await page.goto('/');
  await page.getByRole('button', { name: '録音', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: '録音ファイルを取得できませんでした。' })).toBeVisible();
  expect(downloads).toBe(0);
});

test('records during native audio, shows red, and downloads the saved output', async ({ page }) => {
  const state = await mockSession(page);
  await mockRecording(page);
  state.active = true;
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await expect(record).toBeEnabled();
  await record.click();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  await expect(record).toHaveAttribute('aria-pressed', 'true');
  await expect(record).toHaveCSS('background-color', 'rgb(179, 38, 30)');
  await expect(page.getByRole('button', { name: 'パススルー' })).toBeEnabled();
  expect(state.config.recording_started).toBe(true);
  const downloadPromise = page.waitForEvent('download');
  await record.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('output.wav');
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  await expect(record).toHaveAttribute('aria-pressed', 'false');
  expect(state.config.recording_started).toBe(false);
});

test('recording may be armed and cancelled while stopped, including with passthrough', async ({ page }) => {
  const state = await mockSession(page);
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await expect(record).toBeEnabled();
  await record.click();
  await expect(record).toContainText('録音待機');
  await expect(record).toHaveAttribute('aria-pressed', 'true');
  expect(state.writes).toHaveLength(0);
  await record.click();
  await expect(record).toHaveAttribute('aria-pressed', 'false');
  state.active = true;
  state.config.pass_through = true;
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(record).toBeEnabled();
  expect(state.writes).toHaveLength(0);
});

test('automatically records successive takes and returns to armed state', async ({ page }) => {
  const state = await mockSession(page);
  await mockRecording(page);
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await record.click();
  for (let take = 0; take < 2; take++) {
    await page.getByRole('button', { name: '開始', exact: true }).click();
    await expect(record).toContainText('録音中');
    expect(state.config.recording_started).toBe(true);
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: '停止', exact: true }).click();
    expect((await download).suggestedFilename()).toBe('output.wav');
    await expect(record).toContainText('録音待機');
    expect(state.config.recording_started).toBe(false);
  }
  expect(state.operations).toEqual(['start', 'stop', 'start', 'stop']);
  await record.click();
  await expect(record).toHaveAttribute('aria-pressed', 'false');
});

test('failed start preserves recording readiness', async ({ page }) => {
  const state = await mockSession(page);
  state.startStatus = 503;
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await record.click();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  await expect(record).toContainText('録音待機');
  expect(state.config.recording_started).toBe(false);
});

test('audio still stops and reports a failed recording save', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.recording_started = true;
  let downloads = 0;
  page.on('download', () => { downloads++; });
  await page.goto('/');
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled();
  state.putStatus = 503;
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('HTTP 503');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  expect(state.operations).toEqual(['stop']);
  expect(downloads).toBe(0);
});

test('recording may be stopped after audio has stopped', async ({ page }) => {
  const state = await mockSession(page);
  state.config.recording_started = true;
  await mockRecording(page);
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await expect(record).toBeEnabled();
  await record.click();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  expect(state.config.recording_started).toBe(false);
});

test('does not download a recording after a failed save', async ({ page }) => {
  const state = await mockSession(page);
  state.config.recording_started = true;
  state.putStatus = 503;
  let downloads = 0;
  page.on('download', () => { downloads++; });
  await page.goto('/');
  await page.getByRole('button', { name: '録音', exact: true }).click();
  await expect(page.locator('main > .configuration-status').getByRole('alert')).toContainText('HTTP 503');
  expect(downloads).toBe(0);
});
