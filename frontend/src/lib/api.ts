import type { ModelCatalog, ModelSummary } from './catalog';
import { ApiError } from './api-error';
import type { ConfigurationSnapshot } from './settings';
import type { AudioDevice, AudioDevices } from './audio-devices';

const configurationUrl = '/api/configuration-manager/configuration';

function invalidResponse(): never {
  throw new ApiError('invalid_response');
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalidResponse();
  return value as Record<string, unknown>;
}

function text(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value !== 'string') invalidResponse();
  return value;
}

function numeric(value: unknown): number | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) invalidResponse();
  return value;
}

function boolean(value: unknown): boolean | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'boolean') invalidResponse();
  return value;
}

function parseSettings(config: Record<string, unknown>): ConfigurationSnapshot {
  const mode = config.voice_changer_input_mode ?? null;
  if (mode !== null && mode !== 'server' && mode !== 'client') invalidResponse();
  return {
    inputMode: mode,
    inputGain: numeric(config.audio_input_device_gain),
    outputGain: numeric(config.audio_output_device_gain),
    monitorGain: numeric(config.audio_monitor_device_gain),
    inputDevice: numeric(config.audio_input_device_index),
    outputDevice: numeric(config.audio_output_device_index),
    monitorDevice: numeric(config.audio_monitor_device_index),
    inputDeviceRate: numeric(config.audio_input_device_sample_rate),
    outputDeviceRate: numeric(config.audio_output_device_sample_rate),
    monitorDeviceRate: numeric(config.audio_monitor_device_sample_rate),
    gpuDevice: numeric(config.gpu_device_id_int),
    wasapiExclusive: boolean(config.wasapi_exclude_emabled),
    highPassEnabled: boolean(config.enable_high_pass_filter),
    highPassCutoff: numeric(config.high_pass_filter_cutoff),
    lowPassEnabled: boolean(config.enable_low_pass_filter),
    lowPassCutoff: numeric(config.low_pass_filter_cutoff),
    noiseGate: numeric(config.noise_gate),
    extraSeconds: numeric(config.extra_frame_sec),
    ioAnalysisEnabled: boolean(config.realtime_output_status_enabled),
    ioAnalysisInterval: numeric(config.realtime_output_status_send_interval_sec),
    processAnalysisEnabled: boolean(config.realtime_process_status_enabled),
    processAnalysisInterval: numeric(config.realtime_process_status_send_interval_sec),
  };
}

function modelImage(id: number, value: unknown): string | null {
  // Backends may serialize Windows paths; static serving uses the slot's basename.
  const filename = text(value).replaceAll('\\', '/').split('/').at(-1);
  if (!filename || filename === '.' || filename === '..') return null;
  return `/model_dir/${id}/${encodeURIComponent(filename)}`;
}

function parseCatalog(slots: unknown, configuration: unknown): ModelCatalog {
  if (!Array.isArray(slots)) invalidResponse();
  const config = object(configuration);
  if (!Number.isSafeInteger(config.current_slot_index)) invalidResponse();
  const currentId = config.current_slot_index as number;
  const ids = new Set<number>();
  const models: ModelSummary[] = [];

  for (const value of slots) {
    const slot = object(value);
    if (!Number.isSafeInteger(slot.slot_index) || (slot.slot_index as number) < 0) invalidResponse();
    const id = slot.slot_index as number;
    if (ids.has(id)) invalidResponse();
    ids.add(id);
    if (slot.voice_changer_type === null) continue;
    if (typeof slot.voice_changer_type !== 'string') invalidResponse();

    const type = slot.voice_changer_type;
    const tags = type === 'RVC' ? [type] : [];
    if (type === 'RVC') {
      if (typeof slot.is_onnx !== 'boolean' || typeof slot.is_f0 !== 'boolean') invalidResponse();
      tags.push(`${slot.is_onnx ? 'onnx' : 'pth'} ${text(slot.version)}`.trim());
      tags.push(slot.is_f0 ? 'f0' : 'non-f0');
      const embedder = text(slot.embedder);
      if (embedder) tags.push(embedder);
    }
    models.push({
      id,
      name: text(slot.name),
      description: text(slot.description),
      imageUrl: modelImage(id, slot.icon_file),
      status: type === 'RVC' ? 'ready' : type === 'RESERVED_FOR_SAMPLE' ? 'pending' : type === 'BROKEN' ? 'broken' : 'unsupported',
      tags,
      settings: type === 'RVC' ? {
        pitch: numeric(slot.pitch_shift),
        indexRatio: numeric(slot.index_ratio),
        pitchEstimator: text(slot.pitch_estimator) || null,
        embedder: text(slot.embedder) || null,
        chunkSeconds: numeric(slot.chunk_sec),
      } : null,
    });
  }

  return {
    models: models.sort((a, b) => a.id - b.id),
    currentModelId: currentId >= 0 ? currentId : null,
    settings: parseSettings(config),
  };
}

async function responseJson(response: Response, signal: AbortSignal): Promise<unknown> {
  if (!response.ok) throw new ApiError('http', response.status);
  try {
    return await response.json();
  } catch (error) {
    if (signal.aborted) throw error;
    invalidResponse();
  }
}

async function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  return responseJson(await fetch(path, { method: 'GET', signal, cache: 'no-store' }), signal);
}

export async function loadModelCatalog(signal: AbortSignal): Promise<ModelCatalog> {
  const [slots, configuration] = await Promise.all([
    getJson('/api/slot-manager/slots', signal),
    getJson(configurationUrl, signal),
  ]);
  return parseCatalog(slots, configuration);
}

function parseDevices(value: unknown): AudioDevice[] {
  if (!Array.isArray(value)) invalidResponse();
  const ids = new Set<number>();
  return value.map(item => {
    const device = object(item);
    if (!Number.isSafeInteger(device.index) || (device.index as number) < 0) invalidResponse();
    const id = device.index as number;
    if (ids.has(id)) invalidResponse();
    ids.add(id);
    if (typeof device.name !== 'string' || !device.name.trim()) invalidResponse();
    if (typeof device.host_api !== 'string') invalidResponse();
    return { id, name: device.name, host: device.host_api };
  });
}

export async function loadAudioDevices(signal: AbortSignal): Promise<AudioDevices> {
  // Read the backend's cached lists; reload=true would reinitialize PortAudio.
  const [input, output] = await Promise.all([
    getJson('/api/audio-device-manager/input_devices', signal),
    getJson('/api/audio-device-manager/output_devices', signal),
  ]);
  return { input: parseDevices(input), output: parseDevices(output) };
}
