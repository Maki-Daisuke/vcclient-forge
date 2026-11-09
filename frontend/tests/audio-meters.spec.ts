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
