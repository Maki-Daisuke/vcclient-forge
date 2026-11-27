import { test, expect, type Page } from '@playwright/test';
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { openControlSections } from './catalog-fixtures';

interface BackendAudioDevice {
  index: number;
  name: string;
  host_api: string;
}

interface StartedBackend {
  baseUrl: string;
  stop: () => Promise<void>;
  logs: () => string;
}

const testsDir = import.meta.dirname;
const repoRoot = path.resolve(testsDir, '..', '..');
const backendDir = path.join(repoRoot, 'backend');
const backendMain = path.join(backendDir, 'main.py');
const venvPython = process.platform === 'win32'
  ? path.join(backendDir, '.venv', 'Scripts', 'python.exe')
  : path.join(backendDir, '.venv', 'bin', 'python');

function missingBackendDependencies(): string[] {
  if (!fs.existsSync(venvPython)) return ['backend/.venv'];
  const probe = spawnSync(venvPython, ['-c',
    'import importlib.util, json; print(json.dumps([name for name in ("pydantic", "fastapi", "onnxruntime", "numpy", "onnx", "torch", "faiss", "sounddevice") if importlib.util.find_spec(name) is None]))',
  ], { encoding: 'utf-8', timeout: 30_000 });
  if (probe.error || probe.status !== 0) {
    throw new Error(`Failed to check backend dependencies: ${probe.error?.message ?? probe.stderr}`);
  }
  return JSON.parse(probe.stdout) as string[];
}

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        server.close(() => reject(new Error('Failed to allocate a TCP port')));
        return;
      }
      server.close(err => (err ? reject(err) : resolve(address.port)));
    });
  });
}

function linkDir(target: string, dest: string): void {
  fs.symlinkSync(target, dest, process.platform === 'win32' ? 'junction' : 'dir');
}

function listModelDirs(repoModelDir: string): string[] {
  if (!fs.existsSync(repoModelDir)) return [];
  return fs.readdirSync(repoModelDir, { withFileTypes: true })
    .filter(dirent =>
      (dirent.isDirectory() || dirent.isSymbolicLink())
      && !dirent.name.startsWith('.')
      && fs.existsSync(path.join(repoModelDir, dirent.name, 'params.json')))
    .map(dirent => dirent.name);
}

function isColdAssetState(): boolean {
  const repoModules = path.join(repoRoot, 'modules');
  const modulesReady = fs.existsSync(repoModules) && fs.readdirSync(repoModules).length >= 4;
  const modelsReady = listModelDirs(path.join(repoRoot, 'model_dir')).length > 0;
  return !modulesReady || !modelsReady;
}

function prepareIsolatedWorkdir(workdir: string): void {
  const repoModules = path.join(repoRoot, 'modules');
  fs.mkdirSync(repoModules, { recursive: true });
  // Share downloaded real RVC ONNX modules in repoRoot without mutating developer settings.
  linkDir(repoModules, path.join(workdir, 'modules'));

  const repoModelDir = path.join(repoRoot, 'model_dir');
  fs.mkdirSync(repoModelDir, { recursive: true });
  const modelDirs = listModelDirs(repoModelDir);
  if (modelDirs.length > 0) {
    // Link existing real model directories and copy catalog.json so writes stay inside workdir.
    const workModelDir = path.join(workdir, 'model_dir');
    fs.mkdirSync(workModelDir, { recursive: true });
    for (const dirname of modelDirs) {
      linkDir(path.join(repoModelDir, dirname), path.join(workModelDir, dirname));
    }
    const catalogPath = path.join(repoModelDir, 'catalog.json');
    if (fs.existsSync(catalogPath)) {
      fs.copyFileSync(catalogPath, path.join(workModelDir, 'catalog.json'));
    }
    return;
  }

  // Empty repo model_dir (e.g. cold CI cache): let real main.py download initial sample models into repoModelDir.
  linkDir(repoModelDir, path.join(workdir, 'model_dir'));
}

function resolvePythonCommand(port: number): { command: string; args: string[] } {
  if (fs.existsSync(venvPython)) {
    return { command: venvPython, args: [backendMain, '--host', '127.0.0.1', '--port', String(port)] };
  }
  return {
    command: 'uv',
    args: ['run', '--no-sync', '--project', backendDir, 'python', backendMain, '--host', '127.0.0.1', '--port', String(port)],
  };
}

function waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true);
  return new Promise(resolve => {
    const timer = setTimeout(() => {
      child.off('close', onClose);
      resolve(false);
    }, timeoutMs);
    const onClose = () => {
      clearTimeout(timer);
      resolve(true);
    };
    child.once('close', onClose);
  });
}

async function startBackend(coldAssets: boolean): Promise<StartedBackend> {
  const port = await findFreePort();
  const workdir = fs.mkdtempSync(path.join(os.tmpdir(), 'vcclient-e2e-'));
  prepareIsolatedWorkdir(workdir);
  const { command, args } = resolvePythonCommand(port);
  const output: string[] = [];

  const child = spawn(command, args, {
    cwd: workdir,
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout?.on('data', chunk => output.push(String(chunk)));
  child.stderr?.on('data', chunk => output.push(String(chunk)));

  const baseUrl = `http://127.0.0.1:${port}`;
  const stop = async () => {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill('SIGTERM');
      const exited = await waitForExit(child, 5_000);
      if (!exited) {
        child.kill('SIGKILL');
        await waitForExit(child, 5_000);
      }
    }
    fs.rmSync(workdir, { recursive: true, force: true });
  };

  const startupTimeoutMs = coldAssets ? 600_000 : 90_000;
  const deadline = Date.now() + startupTimeoutMs;
  try {
    while (Date.now() < deadline) {
      if (child.exitCode !== null) {
        throw new Error(`Backend exited early (${child.exitCode}):\n${output.join('')}`);
      }
      try {
        const res = await fetch(`${baseUrl}/api/settings`);
        if (res.ok) {
          return { baseUrl, stop, logs: () => output.join('') };
        }
      } catch {
        // Retry until the backend HTTP server is listening.
      }
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    throw new Error(`Timed out waiting for backend on ${baseUrl}:\n${output.join('')}`);
  } catch (err) {
    await stop();
    throw err;
  }
}

async function ensureModelSelected(page: Page): Promise<void> {
  const cards = page.locator('.model-card');
  await expect(cards.first()).toBeVisible({ timeout: 15_000 });
  if ((await page.locator('.model-card.selected').count()) === 0) {
    await cards.first().click();
    await expect(page.locator('.model-card.selected')).toHaveCount(1);
  }
}

async function muteOutputSlider(page: Page): Promise<void> {
  const outputGain = page.getByRole('slider', { name: '出力音量', exact: true });
  await outputGain.focus();
  await outputGain.press('Home');
  await expect(outputGain).toHaveAttribute('aria-valuenow', '0');
}

// Use Chromium's built-in fake media device & auto-grant UI because headless/CI browsers have no physical microphone.
test.use({
  launchOptions: {
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  },
});

test.describe.configure({ mode: 'serial' });

test.describe('full-stack UI + real backend/main.py', () => {
  let backend: StartedBackend;

  test.beforeAll(() => {
    const missing = missingBackendDependencies();
    if (missing.length > 0) {
      const reason = `Backend dependencies are not installed (${missing.join(', ')}). Run npm run build:backend -- --edition <edition>.`;
      console.warn(`[full-stack] Skipping tests: ${reason}`);
      test.skip(true, reason);
    }
  });

  test.beforeEach(async ({}, testInfo) => {
    const coldAssets = isColdAssetState();
    testInfo.setTimeout(coldAssets ? 660_000 : 120_000);
    backend = await startBackend(coldAssets);
  });

  test.afterEach(async ({}, testInfo) => {
    if (testInfo.status !== testInfo.expectedStatus && backend) {
      await testInfo.attach('backend-logs', { body: backend.logs(), contentType: 'text/plain' });
    }
    if (backend) {
      await backend.stop();
    }
  });

  test('client mode converts real audio over WebSocket through unmodified main.py', async ({ page, request }) => {
    let sentAudioFrames = 0;
    let receivedAudioFrames = 0;
    let receivedAudioBytes = 0;

    page.on('websocket', ws => {
      if (!ws.url().endsWith('/api/ws/audio')) return;
      ws.on('framesent', ({ payload }) => {
        if (Buffer.isBuffer(payload) && payload.byteLength > 0) sentAudioFrames++;
      });
      ws.on('framereceived', ({ payload }) => {
        if (Buffer.isBuffer(payload) && payload.byteLength > 0) {
          receivedAudioFrames++;
          receivedAudioBytes += payload.byteLength;
        }
      });
    });

    await page.addInitScript(() => {
      localStorage.setItem('vcclient-forge.ui-preferences.v1', '{"language":"ja","theme":"light"}');
    });

    await page.goto(backend.baseUrl);
    await ensureModelSelected(page);
    await openControlSections(page);
    await page.getByRole('group', { name: '入出力モード' }).getByText('クライアントモード', { exact: true }).click();
    await muteOutputSlider(page);

    const startButton = page.getByRole('button', { name: '開始', exact: true });
    await expect(startButton).toBeEnabled();
    await startButton.click();

    const stopButton = page.getByRole('button', { name: '停止', exact: true });
    await expect(stopButton).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole('alert')).toHaveCount(0);

    const runningRes = await request.get(`${backend.baseUrl}/api/session`);
    expect(runningRes.ok()).toBe(true);
    const runningSession = await runningRes.json();
    expect(runningSession.status).toBe('running');
    expect(runningSession.snapshot?.input_mode).toBe('client');

    // Verify browser microphone frames actually reach the backend ONNX pipeline and return converted PCM frames.
    await expect.poll(() => sentAudioFrames, { timeout: 20_000 }).toBeGreaterThan(0);
    await expect.poll(() => receivedAudioFrames, { timeout: 30_000 }).toBeGreaterThan(0);
    expect(receivedAudioBytes).toBeGreaterThan(0);
    expect(receivedAudioBytes % 4).toBe(0);
    await expect(page.getByRole('alert')).toHaveCount(0);

    await stopButton.click();
    await expect(startButton).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('alert')).toHaveCount(0);

    const stoppedSession = await (await request.get(`${backend.baseUrl}/api/session`)).json();
    expect(stoppedSession.status).toBe('stopped');
  });

  test('server mode opens real PortAudio streams via unmodified main.py Start button', async ({ page, request }) => {
    const devicesRes = await request.get(`${backend.baseUrl}/api/devices/audio`);
    if (!devicesRes.ok()) {
      test.skip(true, `Audio device backend is unavailable in this environment (${devicesRes.status()})`);
    }
    const audioDevices = await devicesRes.json() as { inputs: BackendAudioDevice[]; outputs: BackendAudioDevice[] };
    if (!audioDevices.inputs.length || !audioDevices.outputs.length) {
      test.skip(true, 'No host PortAudio input/output devices available in this environment');
    }

    const pick = (list: BackendAudioDevice[]) =>
      list.find(device => /wasapi/i.test(device.host_api)) ?? list[0];
    const input = pick(audioDevices.inputs);
    const output = pick(audioDevices.outputs);

    await page.addInitScript(() => {
      localStorage.setItem('vcclient-forge.ui-preferences.v1', '{"language":"ja","theme":"light"}');
    });

    await page.goto(backend.baseUrl);
    await ensureModelSelected(page);
    await openControlSections(page);
    await page.getByRole('group', { name: '入出力モード' }).getByText('サーバーモード', { exact: true }).click();
    await muteOutputSlider(page);

    await page.getByRole('combobox', { name: '入力デバイス（マイク）', exact: true }).selectOption(String(input.index));
    await page.getByRole('combobox', { name: '出力デバイス（スピーカー）', exact: true }).selectOption(String(output.index));

    const startButton = page.getByRole('button', { name: '開始', exact: true });
    await expect(startButton).toBeEnabled();
    await startButton.click();

    const stopButton = page.getByRole('button', { name: '停止', exact: true });
    await expect(stopButton).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole('alert')).toHaveCount(0);

    const runningSession = await (await request.get(`${backend.baseUrl}/api/session`)).json();
    expect(runningSession.status).toBe('running');
    expect(runningSession.snapshot?.input_mode).toBe('server');

    await page.waitForTimeout(300);
    await expect(page.getByRole('alert')).toHaveCount(0);

    await stopButton.click();
    await expect(startButton).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('alert')).toHaveCount(0);

    const stoppedSession = await (await request.get(`${backend.baseUrl}/api/session`)).json();
    expect(stoppedSession.status).toBe('stopped');
  });
});
