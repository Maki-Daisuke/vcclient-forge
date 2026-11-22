import { expect, type Page, type Route } from '@playwright/test';

// NanoID models in catalog.json display order.
export const slots = [
  {
    id: 'model_a',
    name: 'Test model A',
    sample_rate: 40000,
    supports_f0: true,
    has_index: true,
    embedder: 'hubert_base_japanese_l12',
    version: 'v2',
    has_icon: false,
    icon_revision: 0,
    pitch_shift: 3,
    index_ratio: 0.25,
    chunk_sec: 0.5,
    pitch_estimator: 'fcpe',
  },
  {
    id: 'model_b',
    name: 'Test model B',
    sample_rate: 40000,
    supports_f0: false,
    has_index: false,
    embedder: 'hubert_base_l12',
    version: 'v1',
    has_icon: true,
    icon_revision: 1,
    pitch_shift: -5,
    index_ratio: 0.63,
    chunk_sec: 0.3,
    pitch_estimator: 'rmvpe',
  },
];

export const LOCKED_SESSION_FIELDS = [
  'model_id',
  'chunk_sec',
  'pitch_estimator',
  'extra_frame_sec',
  'compute_device_id',
  'input_mode',
  'audio_input_device_index',
  'audio_output_device_index',
  'audio_monitor_device_index',
  'audio_input_device_sample_rate',
  'audio_output_device_sample_rate',
  'audio_monitor_device_sample_rate',
  'wasapi_exclusive_enabled',
];

export const configuration = {
  model_id: 'model_b' as string | null,
  input_mode: 'server' as 'server' | 'client',
  compute_device_id: 2,
  extra_frame_sec: 0.68,
  audio_input_device_index: 8,
  audio_output_device_index: 11,
  audio_monitor_device_index: -1,
  audio_input_device_sample_rate: 44100,
  audio_output_device_sample_rate: 48000,
  audio_monitor_device_sample_rate: -1,
  wasapi_exclusive_enabled: true,
  input_gain: 2.7,
  output_gain: 0.65,
  enable_high_pass_filter: true,
  high_pass_filter_cutoff: 140,
  enable_low_pass_filter: false,
  low_pass_filter_cutoff: 9500,
  noise_gate: -55,
  enable_performance_monitor: true,
  realtime_process_status_enabled: false,
  realtime_output_status_enabled: true,
};

export const stoppedSessionState = {
  status: 'stopped' as const,
  snapshot: null,
  locked_fields: LOCKED_SESSION_FIELDS,
  input_sample_rate: null as number | null,
  output_sample_rate: null as number | null,
  monitor_sample_rate: null as number | null,
  last_error: null,
};

export const computeDevices = [
  { id: 0, name: 'CPU' },
  { id: 1, name: '[CUDA] NVIDIA Test GPU' },
  { id: 2, name: '[DirectML] Test GPU' },
];

export const inputDevices = [
  { index: 11, name: 'Other microphone', host_api: 'MME' },
  { index: 8, name: 'USB microphone', host_api: 'Windows WASAPI' },
];

export const outputDevices = [
  { index: 25, name: 'Monitor headphones', host_api: 'Windows WASAPI' },
  { index: 11, name: 'USB speakers', host_api: 'Windows WASAPI' },
];

export async function fulfillCatalog(route: Route, data: unknown = slots, currentId: string | null = 'model_b') {
  expect(route.request().method()).toBe('GET');
  const path = new URL(route.request().url()).pathname;
  if (path === '/api/models') {
    await route.fulfill({ json: data });
  } else if (path === '/api/settings') {
    await route.fulfill({
      headers: { ETag: '"settings-1"' },
      json: { ...configuration, model_id: currentId },
    });
  } else if (path === '/api/session') {
    await route.fulfill({
      headers: { ETag: '"session-1"' },
      json: stoppedSessionState,
    });
  } else if (path === '/api/devices/compute') {
    await route.fulfill({ json: computeDevices });
  } else if (path === '/api/devices/audio') {
    await route.fulfill({ json: { inputs: inputDevices, outputs: outputDevices } });
  } else if (/^\/api\/models\/[^/]+\/icon$/.test(path)) {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="steelblue"/></svg>',
    });
  } else {
    throw new Error(`Unexpected API request: ${path}`);
  }
}

export async function mockCatalog(page: Page) {
  await page.route('**/api/**', route => fulfillCatalog(route));
  await mockModelImages(page);
}

export async function mockModelImages(page: Page) {
  await page.route('**/api/models/*/icon**', route => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="steelblue"/></svg>',
  }));
}

export async function openControlSections(page: Page) {
  const names = ['inference', 'input', 'volume', 'noise'] as const;
  const summaries = await page.locator('.controls-column > details.control-group > summary').all();
  for (const [index, summary] of summaries.entries()) {
    if (!await summary.locator('..').evaluate(element => (element as HTMLDetailsElement).open)) await summary.click();
    await waitForControlSection(page, names[index]);
  }
}

export async function waitForControlSection(page: Page, name: string, open = true) {
  await expect.poll(() => page.evaluate(({ key, expected }) => {
    try { return JSON.parse(localStorage.getItem('vcclient-forge.control-sections.v1') ?? '{}')[key] === expected; }
    catch { return true; }
  }, { key: name, expected: open })).toBe(true);
}
