import { expect, test, type Page, type WebSocketRoute } from '@playwright/test';
import { mockSession } from './session-fixtures';

async function displaySetting(page: Page) {
  await page.getByRole('button', { name: '詳細設定', exact: true }).click();
  return page.getByRole('dialog').getByRole('checkbox', { name: 'リアルタイム表示' });
}

test('switches both backend analysis settings while audio is running and preserves intervals', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  state.config.realtime_process_status_enabled = true;
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket(/\/socket\.io\//, ws => {
    socket = ws;
    ws.onMessage(message => { if (message === '40/test,') ws.send('40/test,{"sid":"test"}'); });
    ws.send('0{"sid":"test","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}');
  });
  await page.goto('/');
  await expect.poll(() => Boolean(socket)).toBe(true);
  socket!.send(`42/test,${JSON.stringify(['data', ['realtime_output_status', JSON.stringify({ inputRms: 0.5, outputRms: 0.5, outputBufferSize: 4800 })]])}`);
  await expect.poll(async () => parseFloat(await page.locator('.meter > span').first().evaluate(element => element.style.getPropertyValue('--empty')))).toBeLessThan(100);
  const setting = await displaySetting(page);
  await expect(setting).toBeChecked();
  await setting.uncheck();
  await expect.poll(() => state.config.realtime_output_status_enabled).toBe(false);
  expect(state.config.realtime_process_status_enabled).toBe(false);
  expect(state.config.realtime_output_status_send_interval_sec).toBe(0.4);
  expect(state.config.realtime_process_status_send_interval_sec).toBe(2.2);
  await expect(page.locator('.meter > span').first()).toHaveAttribute('style', /--empty:\s*100%/);
  for (const value of await page.locator('.performance dl dd').all()) await expect(value).toHaveText('—');
  await setting.check();
  await expect.poll(() => state.config.realtime_output_status_enabled).toBe(true);
  expect(state.config.realtime_process_status_enabled).toBe(true);
  expect(state.config.enable_performance_monitor).toBe(true);
  await page.keyboard.press('Escape');
  await page.reload();
  await expect(await displaySetting(page)).toBeChecked();
});

test('repairs mixed settings and restores the performance monitor when enabled', async ({ page }) => {
  const state = await mockSession(page);
  state.config.realtime_output_status_enabled = true;
  state.config.realtime_process_status_enabled = false;
  state.config.enable_performance_monitor = false;
  await page.goto('/');
  const setting = await displaySetting(page);
  expect(await setting.evaluate(element => (element as HTMLInputElement).indeterminate)).toBe(true);
  await setting.check();
  await expect.poll(() => state.config.realtime_process_status_enabled).toBe(true);
  expect(state.config.enable_performance_monitor).toBe(true);
});

test('retains a failed change and allows retry inside advanced settings', async ({ page }) => {
  const state = await mockSession(page);
  state.config.realtime_process_status_enabled = true;
  state.putStatus = 503;
  await page.goto('/');
  const setting = await displaySetting(page);
  await setting.uncheck();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('alert')).toContainText('HTTP 503');
  expect(state.config.realtime_output_status_enabled).toBe(true);
  state.putStatus = 200;
  await dialog.getByRole('button', { name: '保存を再試行' }).click();
  await expect.poll(() => state.config.realtime_output_status_enabled).toBe(false);
  expect(state.config.realtime_process_status_enabled).toBe(false);
  await expect(dialog.getByRole('alert')).toHaveCount(0);
});
