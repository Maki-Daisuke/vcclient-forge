import { expect, test, type WebSocketRoute } from '@playwright/test';
import { openControlSections } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

test('switches to client mode and reports a denied microphone without starting audio', async ({ page }) => {
  const state = await mockSession(page);
  state.config.output_sample_rate = 48000;
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
      value: () => Promise.reject(new DOMException('Permission denied', 'NotAllowedError')),
    });
  });
  await page.goto('/');
  await openControlSections(page);
  await page.getByText('クライアントモード', { exact: true }).click();
  await expect.poll(() => state.config.voice_changer_input_mode).toBe('client');
  await expect(page.getByRole('button', { name: 'マイクを許可してデバイスを取得' })).toBeEnabled();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('マイクの許可');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeVisible();
  expect(state.operations).not.toContain('start');
});

test('streams microphone samples over Socket.IO and releases the microphone on stop', async ({ page }) => {
  const state = await mockSession(page);
  state.config.output_sample_rate = 48000;
  state.config.voice_changer_input_mode = 'client';
  state.config.realtime_process_status_enabled = true;
  let packets = 0;
  const sockets: WebSocketRoute[] = [];
  await page.routeWebSocket(/\/socket\.io\//, socket => {
    socket.send('0{"sid":"test","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}');
    socket.onMessage(message => {
      if (typeof message === 'string' && message.startsWith('40/test,')) {
        socket.send('40/test,{"sid":"test"}');
        sockets.push(socket);
      }
      if (message instanceof Buffer) {
        packets++;
        socket.send('451-/test,["response",0,{"_placeholder":true,"num":0},"{}"]');
        socket.send(Buffer.from(new Float32Array(2048).buffer));
      }
    });
  });
  await page.addInitScript(() => {
    const originalStart = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (...args) {
      (window as unknown as { played: number }).played = ((window as unknown as { played: number }).played ?? 0) + 1;
      return originalStart.apply(this, args);
    };
    const audio = new AudioContext();
    const oscillator = audio.createOscillator();
    const destination = audio.createMediaStreamDestination();
    oscillator.connect(destination);
    oscillator.start();
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => destination.stream });
    (window as unknown as { testStream: MediaStream }).testStream = destination.stream;
  });
  await page.goto('/');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  await expect.poll(() => packets).toBeGreaterThan(0);
  await expect.poll(() => page.evaluate(() => (window as unknown as { played: number }).played ?? 0), { timeout: 10000 }).toBeGreaterThan(0);
  const passthrough = page.getByRole('button', { name: 'パススルー' });
  await passthrough.click();
  await expect.poll(() => state.config.pass_through).toBe(true);
  await expect(passthrough).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => sockets.length).toBeGreaterThanOrEqual(2);
  const event = `42/test,${JSON.stringify(['data', ['realtime_process_status', JSON.stringify({ inputBufferSize: 4800, elapsedTime: 0.05 })]])}`;
  for (const socket of sockets) socket.send(event);
  const metrics = page.locator('.performance dl > div');
  await expect(metrics.nth(0)).toContainText('0.100 s');
  await expect(metrics.nth(1)).toContainText('—');
  await expect(metrics.nth(2)).toContainText('0.050 s');
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeVisible();
  await expect(metrics.nth(0)).toContainText('—');
  await expect(metrics.nth(2)).toContainText('—');
  expect(await page.evaluate(() => (window as unknown as { testStream: MediaStream }).testStream.getTracks()[0].readyState)).toBe('ended');
});
