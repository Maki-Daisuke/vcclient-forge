import { expect, test, type WebSocketRoute } from '@playwright/test';
import { openControlSections } from './catalog-fixtures';
import { mockSession } from './session-fixtures';

test('shows automatic gain in the volume section only in client mode', async ({ page }) => {
  await mockSession(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getSupportedConstraints', { value: () => ({ autoGainControl: true }) });
  });
  await page.goto('/');
  await openControlSections(page);
  const autoGain = page.getByRole('checkbox', { name: '自動音量調整' });
  await expect(autoGain).toHaveCount(0);
  await page.getByText('クライアントモード', { exact: true }).click();
  const volume = page.locator('details.control-group').filter({ has: page.locator('summary').getByText('音量コントロール') });
  await expect(volume.getByRole('checkbox', { name: '自動音量調整' })).toBeVisible();
  await expect(volume.getByRole('slider', { name: '入力音量' })).toBeEnabled();
  await volume.getByRole('slider', { name: '入力音量' }).press('ArrowRight');
  await expect(volume.getByRole('slider', { name: '入力音量' })).toHaveAttribute('aria-valuenow', '1.01');
  await autoGain.check();
  await expect(volume.getByRole('slider', { name: '入力音量' })).toBeDisabled();
  await autoGain.uncheck();
  await expect(volume.getByRole('slider', { name: '入力音量' })).toBeEnabled();
  await page.getByText('サーバーモード', { exact: true }).click();
  await expect(autoGain).toHaveCount(0);
  await expect(volume.getByRole('slider', { name: '入力音量' })).toBeEnabled();
  await page.getByText('クライアントモード', { exact: true }).click();
  await expect(volume.getByRole('slider', { name: '入力音量' })).toHaveAttribute('aria-valuenow', '1.01');
  await page.reload();
  await openControlSections(page);
  await expect(volume.getByRole('slider', { name: '入力音量' })).toHaveAttribute('aria-valuenow', '1.01');
});

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
  await expect(page.getByRole('button', { name: 'デバイス再検出' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'デバイス再検出' }).locator('..')).toHaveCSS('justify-content', 'flex-end');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('マイクの許可');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeVisible();
  expect(state.operations).not.toContain('start');
});

test('applies client gains before capture and playback and updates them while running', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  state.config.output_sample_rate = 48000;
  await page.routeWebSocket(/\/socket\.io\//, socket => {
    socket.send('0{"sid":"test","upgrades":[],"pingInterval":25000,"pingTimeout":20000,"maxPayload":1000000}');
    socket.onMessage(message => {
      if (typeof message === 'string' && message.startsWith('40/test,')) socket.send('40/test,{"sid":"test"}');
    });
  });
  await page.addInitScript(() => {
    const original = AudioContext.prototype.createGain;
    AudioContext.prototype.createGain = function () {
      const node = original.call(this);
      const state = window as unknown as { gainNodes: GainNode[] };
      (state.gainNodes ??= []).push(node);
      return node;
    };
    const audio = new AudioContext();
    const destination = audio.createMediaStreamDestination();
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => destination.stream });
  });
  await page.goto('/');
  await openControlSections(page);
  const input = page.getByRole('slider', { name: '入力音量' });
  const output = page.getByRole('slider', { name: '出力音量' });
  await input.press('ArrowRight');
  await output.press('ArrowLeft');
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: '優先デバイス' })).toBeDisabled();
  for (const name of ['優先デバイス', 'チャンクフレーム（秒）', 'Extraフレーム（秒）', 'クロスフェード（秒）']) {
    const group = page.getByRole('group', { name, exact: true });
    await group.hover();
    await expect(group.getByRole('tooltip')).toHaveText('音声の停止中に変更できます。');
    if (name !== '優先デバイス') await expect(page.getByRole('slider', { name })).toBeDisabled();
  }
  const gains = () => page.evaluate(() => (window as unknown as { gainNodes: GainNode[] }).gainNodes.map(node => node.gain.value));
  expect((await gains())[0]).toBeCloseTo(1.01);
  expect((await gains())[1]).toBeCloseTo(0.99);
  await input.press('ArrowRight');
  await output.press('ArrowLeft');
  await expect.poll(async () => (await gains())[0]).toBeCloseTo(1.02);
  await expect.poll(async () => (await gains())[1]).toBeCloseTo(0.98);
});

test('streams microphone samples over Socket.IO and releases the microphone on stop', async ({ page }) => {
  const state = await mockSession(page);
  state.config.output_sample_rate = 48000;
  state.config.voice_changer_input_mode = 'client';
  state.config.realtime_process_status_enabled = true;
  state.models[0].is_f0 = true;
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
        socket.send(Buffer.from(new Float32Array(2048).fill(0.25).buffer));
      }
    });
  });
  await page.addInitScript(() => {
    const originalCreateGain = AudioContext.prototype.createGain;
    AudioContext.prototype.createGain = function () {
      const node = originalCreateGain.call(this);
      const state = window as unknown as { gainNodes: GainNode[] };
      (state.gainNodes ??= []).push(node);
      return node;
    };
    const originalStart = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function (...args) {
      (window as unknown as { played: number }).played = ((window as unknown as { played: number }).played ?? 0) + 1;
      return originalStart.apply(this, args);
    };
    const audio = new AudioContext();
    document.addEventListener('click', () => { void audio.resume(); }, { once: true });
    const oscillator = audio.createOscillator();
    const destination = audio.createMediaStreamDestination();
    oscillator.connect(destination);
    oscillator.start();
    Object.defineProperty(navigator.mediaDevices, 'getSupportedConstraints', { value: () => ({ echoCancellation: true, noiseSuppression: true, autoGainControl: true }) });
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async (constraints: MediaStreamConstraints) => {
      (window as unknown as { capturedConstraints: MediaStreamConstraints }).capturedConstraints = constraints;
      return destination.stream;
    } });
    (window as unknown as { testStream: MediaStream }).testStream = destination.stream;
  });
  await page.goto('/');
  await openControlSections(page);
  const echo = page.getByRole('checkbox', { name: 'エコーキャンセル' });
  const noise = page.getByRole('checkbox', { name: 'ノイズサプレッション', exact: true });
  const autoGain = page.getByRole('checkbox', { name: '自動音量調整' });
  await expect(autoGain).not.toBeChecked();
  await expect(page.getByRole('checkbox', { name: 'ノイズサプレッション2を有効にする' })).toHaveCount(0);
  await echo.check();
  await noise.check();
  await autoGain.check();
  expect(JSON.parse(await page.evaluate(() => localStorage.getItem('vcclient-forge.browser-audio.v1')) ?? '{}'))
    .toEqual({ echoCancellation: true, noiseSuppression: true, autoGainControl: true });
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeEnabled();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('button', { name: '停止', exact: true })).toBeVisible();
  await expect(echo).toBeDisabled();
  await expect(noise).toBeDisabled();
  await expect(autoGain).toBeDisabled();
  for (const checkbox of [echo, noise, autoGain]) {
    const group = checkbox.locator('..').locator('..');
    const tooltip = group.getByRole('tooltip', { includeHidden: true });
    await expect(tooltip).toHaveText('音声の停止中に変更できます。');
    await group.hover();
    await expect(tooltip).toBeVisible();
    await group.focus();
    await expect(tooltip).toBeVisible();
  }
  expect(await page.evaluate(() => (window as unknown as { gainNodes: GainNode[] }).gainNodes.map(node => node.gain.value))).toEqual([1, 1]);
  await page.getByRole('slider', { name: '出力音量' }).press('ArrowRight');
  await expect.poll(() => page.evaluate(() => (window as unknown as { gainNodes: GainNode[] }).gainNodes[1].gain.value)).toBeCloseTo(1.01);
  expect(await page.evaluate(() => (window as unknown as { capturedConstraints: MediaStreamConstraints }).capturedConstraints.audio))
    .toMatchObject({ echoCancellation: { exact: true }, noiseSuppression: { exact: true }, autoGainControl: { exact: true } });
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeDisabled();
  await expect.poll(() => packets).toBeGreaterThan(0);
  await expect.poll(() => page.evaluate(() => (window as unknown as { played: number }).played ?? 0), { timeout: 10000 }).toBeGreaterThan(0);
  const bars = page.locator('.meter > span');
  await expect.poll(async () => Number.parseFloat(await bars.nth(0).evaluate(element => element.style.getPropertyValue('--empty')))).toBeLessThan(100);
  await expect.poll(async () => Number.parseFloat(await bars.nth(1).evaluate(element => element.style.getPropertyValue('--empty')))).toBeLessThan(100);
  await page.getByRole('slider', { name: 'ノイズゲートのしきい値' }).press('ArrowRight');
  await expect.poll(() => state.config.noise_gate).toBe(-54);
  await page.getByRole('slider', { name: 'ハイパスのカットオフ' }).press('ArrowRight');
  await expect.poll(() => state.config.high_pass_filter_cutoff).toBe(141);
  await page.getByRole('checkbox', { name: 'ローパスフィルタを有効にする' }).check();
  await expect.poll(() => state.config.enable_low_pass_filter).toBe(true);
  await page.getByRole('slider', { name: 'ローパスのカットオフ' }).press('ArrowLeft');
  await expect.poll(() => state.config.low_pass_filter_cutoff).toBe(9499);
  const passthrough = page.getByRole('button', { name: 'パススルー' });
  await passthrough.click();
  await expect.poll(() => state.config.pass_through).toBe(true);
  await expect(passthrough).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => sockets.length).toBeGreaterThanOrEqual(2);
  const event = `42/test,${JSON.stringify(['data', ['realtime_process_status', JSON.stringify({ inputBufferSize: 4800, elapsedTime: 0.05 })]])}`;
  for (const socket of sockets) socket.send(event);
  const metrics = page.locator('.performance dl > div');
  await expect(metrics.nth(0)).toContainText('0.100 s');
  await expect(metrics.nth(1)).toContainText(/\d+\.\d{3} s/);
  await expect(page.locator('.buffer-chart .buffer-output')).toHaveCount(1);
  await expect(metrics.nth(2)).toContainText('0.050 s');
  await page.getByRole('button', { name: '停止', exact: true }).click();
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeVisible();
  await expect(page.getByRole('group', { name: '優先デバイス', exact: true })).toHaveCount(0);
  await expect(page.getByRole('radio', { name: 'FCPE' })).toBeEnabled();
  await expect(echo).toBeEnabled();
  await expect(noise).toBeEnabled();
  await expect(autoGain).toBeEnabled();
  for (const checkbox of [echo, noise, autoGain]) {
    await expect(checkbox.locator('..').locator('..').getByRole('tooltip', { includeHidden: true })).toHaveCount(0);
  }
  await expect(metrics.nth(0)).toContainText('—');
  await expect(metrics.nth(1)).toContainText('—');
  await expect(metrics.nth(2)).toContainText('—');
  await expect(bars.nth(0)).toHaveAttribute('style', /--empty:\s*100%/);
  await expect(bars.nth(1)).toHaveAttribute('style', /--empty:\s*100%/);
  expect(await page.evaluate(() => (window as unknown as { testStream: MediaStream }).testStream.getTracks()[0].readyState)).toBe('ended');
  await page.reload();
  await openControlSections(page);
  await expect(echo).toBeChecked();
  await expect(noise).toBeChecked();
  await expect(autoGain).toBeChecked();
});

test('disables processing options that the browser does not support', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  await page.addInitScript(() => {
    Object.defineProperty(navigator.mediaDevices, 'getSupportedConstraints', { value: () => ({}) });
  });
  await page.goto('/');
  await openControlSections(page);
  await expect(page.getByRole('checkbox', { name: 'エコーキャンセル' })).toBeDisabled();
  await expect(page.getByRole('checkbox', { name: 'ノイズサプレッション', exact: true })).toBeDisabled();
  await expect(page.getByRole('checkbox', { name: '自動音量調整' })).toBeDisabled();
});

test('reports failure and releases the microphone if automatic gain control is not applied', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  state.config.output_sample_rate = 48000;
  await page.addInitScript(() => {
    const audio = new AudioContext();
    const destination = audio.createMediaStreamDestination();
    Object.defineProperty(destination.stream.getAudioTracks()[0], 'getSettings', { value: () => ({ autoGainControl: false }) });
    Object.defineProperty(navigator.mediaDevices, 'getSupportedConstraints', { value: () => ({ autoGainControl: true }) });
    Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { value: async () => destination.stream });
    (window as unknown as { testStream: MediaStream }).testStream = destination.stream;
  });
  await page.goto('/');
  await openControlSections(page);
  await page.getByRole('checkbox', { name: '自動音量調整' }).check();
  await page.getByRole('button', { name: '開始', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('The microphone could not enable the requested audio processing.');
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { testStream: MediaStream }).testStream.getTracks()[0].readyState)).toBe('ended');
});

test('allows disabling a saved processing option if browser support is lost', async ({ page }) => {
  const state = await mockSession(page);
  state.config.voice_changer_input_mode = 'client';
  await page.addInitScript(() => {
    localStorage.setItem('vcclient-forge.browser-audio.v1', JSON.stringify({ autoGainControl: true }));
    Object.defineProperty(navigator.mediaDevices, 'getSupportedConstraints', { value: () => ({}) });
  });
  await page.goto('/');
  await openControlSections(page);
  const autoGain = page.getByRole('checkbox', { name: '自動音量調整' });
  await expect(autoGain).toBeChecked();
  await autoGain.uncheck();
  await expect(autoGain).toBeDisabled();
});
