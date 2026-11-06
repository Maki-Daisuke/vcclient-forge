import { expect, type Page, type Route } from '@playwright/test';

// Deliberately sparse and unsorted. UI selection must use IDs, not array positions.
export const slots = [
  {
    slot_index: 7, voice_changer_type: 'RVC', name: 'Test model B',
    description: 'Description of the selected model', icon_file: 'C:\\old\\portrait #1.png',
    is_onnx: false, is_f0: false, version: 'v1', embedder: 'hubert_base_l12',
    pitch_shift: -5, index_ratio: 0.63, pitch_estimator: 'rmvpe', chunk_sec: 0.3,
  },
  { slot_index: 0, voice_changer_type: null },
  {
    slot_index: 2, voice_changer_type: 'RVC', name: 'Test model A',
    description: '', icon_file: null,
    is_onnx: true, is_f0: true, version: 'v2', embedder: 'contentvec',
    pitch_shift: 3, index_ratio: 0.25, pitch_estimator: 'fcpe', chunk_sec: 0.5,
  },
];

export const configuration = {
  current_slot_index: 7,
  voice_changer_input_mode: 'server',
  audio_input_device_gain: 2.7,
  audio_output_device_gain: 0.65,
  audio_monitor_device_gain: 0.35,
  audio_input_device_index: 8,
  audio_output_device_index: 11,
  audio_monitor_device_index: -1,
  audio_input_device_sample_rate: 44100,
  audio_output_device_sample_rate: 48000,
  audio_monitor_device_sample_rate: -1,
  input_sample_rate: 48000,
  gpu_device_id_int: 2,
  wasapi_exclude_emabled: true,
  enable_high_pass_filter: true,
  high_pass_filter_cutoff: 140,
  enable_low_pass_filter: false,
  low_pass_filter_cutoff: 9500,
  noise_gate: -55,
  extra_frame_sec: 0.68,
  realtime_output_status_enabled: true,
  realtime_output_status_send_interval_sec: 0.4,
  realtime_process_status_enabled: false,
  realtime_process_status_send_interval_sec: 2.2,
};

export const inputDevices = [
  { index: 11, name: 'Other microphone', host_api: 'MME' },
  { index: 8, name: 'USB microphone', host_api: 'Windows WASAPI' },
];

export const outputDevices = [
  { index: 25, name: 'Monitor headphones', host_api: 'Windows WASAPI' },
  { index: 11, name: 'USB speakers', host_api: 'Windows WASAPI' },
];

export async function fulfillCatalog(route: Route, data: unknown = slots, currentId = 7) {
  expect(route.request().method()).toBe('GET');
  const path = new URL(route.request().url()).pathname;
  if (path === '/api/slot-manager/slots') {
    await route.fulfill({ json: data });
  } else if (path === '/api/configuration-manager/configuration') {
    await route.fulfill({ json: { ...configuration, current_slot_index: currentId } });
  } else if (path === '/api/audio-device-manager/input_devices') {
    await route.fulfill({ json: inputDevices });
  } else if (path === '/api/audio-device-manager/output_devices') {
    await route.fulfill({ json: outputDevices });
  } else if (path === '/api/local-voice-changer-interface/information') {
    await route.fulfill({ json: { local_voice_changer_interface_active: false } });
  } else if (path === '/api/voice-changer-manager/information') {
    await route.fulfill({ json: { voice_changer_information: { slot_index: currentId, input_sample_rate: 48000, output_sample_rate: 48000 } } });
  } else {
    throw new Error(`Unexpected API request: ${path}`);
  }
}

export async function mockCatalog(page: Page) {
  await page.route('**/api/**', route => fulfillCatalog(route));
  await page.route('**/model_dir/**', route => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="steelblue"/></svg>',
  }));
}
