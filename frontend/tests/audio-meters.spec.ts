import { test, expect, type Page, type WebSocketRoute } from './test-fixtures';
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
  const bar = page.locator('.meter > span');
  await expect(bar.nth(0)).toHaveAttribute('style', /--empty:\s*100%/);
  sendLevels(socket()!, 0.25, 1.4);
  await expect.poll(async () => 1 - parseFloat(await page.locator('.meter > span').nth(0).evaluate(element => element.style.getPropertyValue('--empty'))) / 100).toBeCloseTo((20 * Math.log10(0.25) + 60) / 60);
  await expect(page.locator('.meter > span').nth(1)).toHaveAttribute('style', /--empty:\s*0%/);
  sendLevels(socket()!, -1, 0.5);
  await expect(bar.nth(0)).toHaveAttribute('style', /--empty:\s*100%/, { timeout: 4000 });
  await expect(page.getByText('入出力メーターの情報を取得できません。')).toBeVisible();
  sendLevels(socket()!, 0, 0.5);
  await expect(bar.nth(0)).toHaveAttribute('style', /--empty:\s*100%/);
  await expect.poll(async () => 1 - parseFloat(await bar.nth(1).evaluate(element => element.style.getPropertyValue('--empty'))) / 100).toBeCloseTo((20 * Math.log10(0.5) + 60) / 60);
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(bar.nth(1)).toHaveAttribute('style', /--empty:\s*100%/);
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
  await expect(page.locator('.meter > span').first()).toHaveAttribute('style', /--empty:\s*100%/);
  expect(socket()).toBeUndefined();
});

test('clears levels on disconnect and resumes after reconnecting', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  sendLevels(socket()!, 0.3, 0.4);
  await expect.poll(async () => 1 - parseFloat(await page.locator('.meter > span').first().evaluate(element => element.style.getPropertyValue('--empty'))) / 100).toBeCloseTo((20 * Math.log10(0.3) + 60) / 60);
  const firstSocket = socket()!;
  await firstSocket.close();
  await expect(page.locator('.meter > span').first()).toHaveAttribute('style', /--empty:\s*100%/);
  await expect(page.getByText('入出力メーターの情報を取得できません。')).toBeVisible();
  await expect.poll(() => socket() !== firstSocket, { timeout: 10000 }).toBe(true);
  sendLevels(socket()!, 0.6, 0.7);
  await expect.poll(async () => 1 - parseFloat(await page.locator('.meter > span').first().evaluate(element => element.style.getPropertyValue('--empty'))) / 100).toBeCloseTo((20 * Math.log10(0.6) + 60) / 60);
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
  await expect(page.locator('.meter > span').first()).toHaveAttribute('style', /--empty:\s*100%/);
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


test('displays the most recent valid conversion time independently of buffer data', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  state.config.realtime_process_status_send_interval_sec = 0.1;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  const value = page.getByText('変換時間', { exact: true }).locator('..').locator('dd');
  await expect(value).toHaveText('—');
  sendEvent(socket()!, 'realtime_process_status', { elapsedTime: 0.05, outputSec: 0.2 });
  await expect(value).toHaveText('0.050 s');
  sendEvent(socket()!, 'realtime_process_status', { inputBufferSize: 0, elapsedTime: 0.3, outputSec: 0.2 });
  await expect(value).toHaveText('0.300 s');
  sendEvent(socket()!, 'realtime_process_status', { elapsedTime: 1, outputSec: 0 });
  await expect(value).toHaveText('1.000 s');
  sendEvent(socket()!, 'realtime_process_status', { elapsedTime: -1, outputSec: 0.2 });
  await expect(value).toHaveText('1.000 s');
  sendEvent(socket()!, 'realtime_process_status', { elapsedTime: 0, outputSec: 0.2 });
  await expect(value).toHaveText('0.000 s');
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(value).toHaveText('—');
});

test('clears stale conversion time even when input-buffer updates continue', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  state.config.realtime_process_status_send_interval_sec = 0.1;
  const socket = await mockSocket(page);
  await page.clock.install();
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  const value = page.getByText('変換時間', { exact: true }).locator('..').locator('dd');
  sendEvent(socket()!, 'realtime_process_status', { elapsedTime: 0.05, outputSec: 0.2 });
  await expect(value).toHaveText('0.050 s');
  await page.clock.fastForward(1_000);
  sendEvent(socket()!, 'realtime_process_status', { inputBufferSize: 4800 });
  await expect(page.locator('.performance dl > div').first()).toContainText('0.100 s');
  await page.clock.fastForward(1_100);
  await expect(value).toHaveText('—');
  await expect(page.locator('.performance dl > div').first()).toContainText('0.100 s');
});

test('does not display conversion time when performance monitoring is disabled', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  state.config.enable_performance_monitor = false;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  const value = page.getByText('変換時間', { exact: true }).locator('..').locator('dd');
  sendEvent(socket()!, 'realtime_process_status', { elapsedTime: 0.05, outputSec: 0.2 });
  await expect(value).toHaveText('—');
});


test('keeps conversion time between measurements when the chunk is longer than the reporting interval', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  state.config.realtime_process_status_send_interval_sec = 0.1;
  state.models.find(model => model.slot_index === 7)!.chunk_sec = 5;
  const socket = await mockSocket(page);
  await page.clock.install();
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  const value = page.getByText('変換時間', { exact: true }).locator('..').locator('dd');
  sendEvent(socket()!, 'realtime_process_status', { elapsedTime: 1, outputSec: 5 });
  await expect(value).toHaveText('1.000 s');
  await page.clock.fastForward(5_100);
  await expect(value).toHaveText('1.000 s');
  await page.clock.fastForward(10_000);
  await expect(value).toHaveText('—');
});


test('shows quieter RMS levels on a logarithmic meter with fixed dBFS ticks', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  const socket = await mockSocket(page);
  await page.goto('/');
  await expect.poll(() => Boolean(socket())).toBe(true);
  const bar = page.locator('.meter > span');
  const scale = page.locator('.meter-scale');
  await expect(scale).toHaveCount(2);
  await expect(scale.first().locator('span')).toHaveText(['−60', '−40', '−20', '0 dBFS']);
  const gradient = await bar.first().evaluate(element => getComputedStyle(element).backgroundImage);
  expect(gradient).toContain('rgb(76, 175, 80) 33.333%');
  expect(gradient).toContain('rgb(255, 193, 7) 66.667%');
  expect(gradient).toContain('rgb(244, 67, 54) 83.333%');
  sendLevels(socket()!, 0.1, 0.01);
  await expect.poll(async () => 1 - parseFloat(await bar.nth(0).evaluate(element => element.style.getPropertyValue('--empty'))) / 100).toBeCloseTo(2 / 3);
  await expect.poll(async () => 1 - parseFloat(await bar.nth(1).evaluate(element => element.style.getPropertyValue('--empty'))) / 100).toBeCloseTo(1 / 3);
  sendLevels(socket()!, 0, 1);
  await expect(bar.nth(0)).toHaveAttribute('style', /--empty:\s*100%/);
  await expect(bar.nth(1)).toHaveAttribute('style', /--empty:\s*0%/);
  expect(await bar.first().evaluate(element => getComputedStyle(element).backgroundImage)).toBe(gradient);
});
