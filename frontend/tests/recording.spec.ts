import { expect, test } from '@playwright/test';
import { mockSession } from './session-fixtures';

test('records during native audio, shows red, and downloads the saved output', async ({ page }) => {
  const state = await mockSession(page);
  await page.route('**/output.wav', route => route.fulfill({ contentType: 'audio/wav', headers: { 'content-disposition': 'attachment; filename="output.wav"' }, body: 'recorded audio' }));
  state.active = true;
  await page.goto('/');
  const record = page.getByRole('button', { name: '録音', exact: true });
  await expect(record).toBeEnabled();
  await record.click();
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  await expect(record).toHaveAttribute('aria-pressed', 'true');
  await expect(record).toHaveCSS('background-color', 'rgb(179, 38, 30)');
  await expect(page.getByRole('button', { name: 'パススルー' })).toBeDisabled();
  expect(state.config.recording_started).toBe(true);
  const downloadPromise = page.waitForEvent('download');
  await record.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('output.wav');
  await expect(page.locator('main > .configuration-status')).toHaveAttribute('data-state', 'saved');
  await expect(record).toHaveAttribute('aria-pressed', 'false');
  expect(state.config.recording_started).toBe(false);
});

test('recording may be armed and cancelled while stopped, but not with passthrough', async ({ page }) => {
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
  await expect(record).toBeDisabled();
  expect(state.writes).toHaveLength(0);
});

test('automatically records successive takes and returns to armed state', async ({ page }) => {
  const state = await mockSession(page);
  await page.route('**/output.wav', route => route.fulfill({ contentType: 'audio/wav', headers: { 'content-disposition': 'attachment; filename="output.wav"' }, body: 'recorded audio' }));
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
  await page.route('**/output.wav', route => route.fulfill({ contentType: 'audio/wav', headers: { 'content-disposition': 'attachment; filename="output.wav"' }, body: 'recorded audio' }));
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
