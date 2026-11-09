import { test, expect, type Page, type WebSocketRoute } from '@playwright/test';
import { mockSession } from './session-fixtures';

async function mockSocket(page: Page) {
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket(/\/socket\.io\//, ws => {
    socket = ws;
    ws.onMessage(message => {
      if (message === '40/test,') ws.send('40/test,{"sid":"test"}');
      if (message === '2') ws.send('3');
    });
    ws.send('0{"sid":"test","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}');
  });
  return () => socket;
}

function sendLevels(socket: WebSocketRoute, input: unknown, output: unknown) {
  socket.send(`42/test,${JSON.stringify(['data', ['realtime_output_status', JSON.stringify({ inputRms: input, outputRms: output, realtimeOutputStatusSendIntervalSec: 0.2 })]])}`);
}

function sendEvent(socket: WebSocketRoute, type: string, data: object) {
  socket.send(`42/test,${JSON.stringify(['data', [type, JSON.stringify(data)]])}`);
}

test('displays valid Socket.IO levels, clears stale data, and resumes', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  const labels = page.locator('.performance .meter-label');
  await expect(labels.nth(0)).toContainText('—');
  sendLevels(socket()!, 0.25, 1.4);
  await expect(labels.nth(0)).toContainText('0.250');
  await expect(labels.nth(1)).toContainText('1.400');
  await expect(page.locator('.meter > span').nth(0)).toHaveAttribute('style', /scaleX\(0\.25\)/);
  await expect(page.locator('.meter > span').nth(1)).toHaveAttribute('style', /scaleX\(1\)/);
  sendLevels(socket()!, -1, 0.5);
  await expect(labels.nth(0)).toContainText('0.250');
  await expect(labels.nth(0)).toContainText('—', { timeout: 4000 });
  await expect(page.getByText('入出力メーターの情報を取得できません。')).toBeVisible();
  sendLevels(socket()!, 0, 0.5);
  await expect(labels.nth(0)).toContainText('0.000');
  await expect(labels.nth(1)).toContainText('0.500');
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(labels.nth(0)).toContainText('—');
});

test('does not connect while stopped or when output analysis is disabled', async ({ page }) => {
  const state = await mockSession(page);
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeEnabled();
  expect(socket()).toBeUndefined();
  state.active = true;
  state.config.realtime_output_status_enabled = false;
  await page.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(page.getByText('バックエンドの入出力解析が無効です。')).toBeVisible();
  expect(socket()).toBeUndefined();
});

test('clears levels on disconnect and resumes after reconnecting', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  sendLevels(socket()!, 0.3, 0.4);
  await expect(page.locator('.performance .meter-label').first()).toContainText('0.300');
  const firstSocket = socket()!;
  await firstSocket.close();
  await expect(page.locator('.performance .meter-label').first()).toContainText('—');
  await expect(page.getByText('入出力メーターの情報を取得できません。')).toBeVisible();
  await expect.poll(() => socket() !== firstSocket, { timeout: 10000 }).toBe(true);
  sendLevels(socket()!, 0.6, 0.7);
  await expect(page.locator('.performance .meter-label').first()).toContainText('0.600');
});

test('uses fresh device rates for independent input and output buffer histories', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  state.config.realtime_process_status_send_interval_sec = 0.1;
  state.config.output_sample_rate = 48000;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  // The actual device rates can differ from the values loaded before audio starts.
  state.config.input_sample_rate = 44100;
  state.config.output_sample_rate = 32000;
  sendEvent(socket()!, 'realtime_output_status', { inputRms: 0.1, outputRms: 0.2, outputBufferSize: 3200, realtimeOutputStatusSendIntervalSec: 0.2 });
  sendEvent(socket()!, 'realtime_process_status', { inputBufferSize: 8820 });
  const metrics = page.locator('.performance dl > div');
  await expect(metrics.nth(0)).toContainText('0.200 s');
  await expect(metrics.nth(1)).toContainText('0.100 s');
  await expect(page.locator('.buffer-chart .buffer-input')).toHaveCount(1);
  await expect(page.locator('.buffer-chart .buffer-output')).toHaveCount(1);
  sendEvent(socket()!, 'realtime_process_status', { inputBufferSize: -1 });
  await expect(metrics.nth(0)).toContainText('0.200 s');
  const clear = page.locator('.performance').getByRole('button', { name: 'クリア', exact: true });
  await expect(clear).toBeEnabled();
  await clear.click();
  await expect(page.locator('.buffer-chart polyline')).toHaveCount(0);
  await expect(metrics.nth(0)).toContainText('0.200 s');
  sendEvent(socket()!, 'realtime_output_status', { inputRms: 0.1, outputRms: 0.2, outputBufferSize: 6400, realtimeOutputStatusSendIntervalSec: 1 });
  await expect(metrics.nth(1)).toContainText('0.200 s');
  await expect(metrics.nth(0)).toContainText('—', { timeout: 4000 });
  await expect(metrics.nth(1)).toContainText('0.200 s');
});

test('receives input buffer independently when output analysis is disabled', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_output_status_enabled = false;
  state.config.realtime_process_status_enabled = true;
  state.config.output_sample_rate = 48000;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  sendEvent(socket()!, 'realtime_process_status', { inputBufferSize: 2400 });
  await expect(page.locator('.performance dl > div').first()).toContainText('0.050 s');
  await expect(page.locator('.performance .meter-label').first()).toContainText('—');
});


test('shows only the most recent 20 seconds on a shared time axis', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  state.config.input_sample_rate = 48000;
  state.config.output_sample_rate = 48000;
  const socket = await mockSocket(page);
  const start = Date.now();
  await page.clock.setFixedTime(start);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  sendEvent(socket()!, 'realtime_process_status', { inputBufferSize: 48000 });
  sendEvent(socket()!, 'realtime_output_status', { outputBufferSize: 4800 });
  await expect(page.locator('.buffer-chart .buffer-input')).toHaveCount(1);
  await expect(page.locator('.buffer-chart .buffer-output')).toHaveCount(1);

  await page.clock.setFixedTime(start + 10_000);
  sendEvent(socket()!, 'realtime_output_status', { outputBufferSize: 4800 });
  await expect(page.locator('.buffer-input-point')).toHaveAttribute('cx', '150');
  await expect(page.locator('.buffer-output-point')).toHaveAttribute('cx', '300');

  await page.clock.setFixedTime(start + 21_000);
  sendEvent(socket()!, 'realtime_output_status', { outputBufferSize: 4800 });
  await expect(page.locator('.buffer-chart .buffer-input')).toHaveCount(0);
  await expect(page.locator('.buffer-chart > span')).toHaveText('0.330 s');
  const points = await page.locator('.buffer-output').getAttribute('points');
  expect(points?.trim().split(/\s+/)).toHaveLength(2);
});


test('shows the selected model chunk duration on the buffer scale', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  const line = page.locator('.buffer-chart .buffer-chunk');
  await expect(line).toHaveCount(1);
  await expect(page.locator('.buffer-legend .chunk-label')).toContainText('0.300 s');
  await expect(page.locator('.buffer-chart > span')).toHaveText('0.330 s');
  const initialY = Number(await line.getAttribute('y1'));
  expect(initialY).toBeCloseTo(80 - (0.3 / 0.33) * 80);

  sendEvent(socket()!, 'realtime_process_status', { inputBufferSize: 48000 });
  await expect(page.locator('.buffer-chart > span')).toHaveText('1.100 s');
  const scaledY = Number(await line.getAttribute('y1'));
  expect(scaledY).toBeCloseTo(80 - (0.3 / 1.1) * 80);
  expect(Number(await line.getAttribute('y2'))).toBeCloseTo(scaledY);
});
