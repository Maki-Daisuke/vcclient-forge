import type { ModelCatalog, ModelSummary } from './catalog';
import { ApiError } from './api-error';
import type { ConfigurationSnapshot, ConfigurationEdits, ConfirmedConfiguration, ModelEdits } from './settings';
import type { AudioDevice, AudioDevices } from './audio-devices';

const configurationUrl = '/api/configuration-manager/configuration';
const nativeUrl = '/api/local-voice-changer-interface';

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
    passThrough: boolean(config.pass_through),
    recording: boolean(config.recording_started),
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
    crossfadeSeconds: numeric(config.crossfade_sec),
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

function parseConfiguration(configuration: unknown): ConfirmedConfiguration {
  const config = object(configuration);
  if (!Number.isSafeInteger(config.current_slot_index)) invalidResponse();
  const currentId = config.current_slot_index as number;
  return { currentModelId: currentId >= 0 ? currentId : null, settings: parseSettings(config) };
}

function parseModel(slot: Record<string, unknown>): ModelSummary {
  if (!Number.isSafeInteger(slot.slot_index) || (slot.slot_index as number) < 0) invalidResponse();
  const id = slot.slot_index as number;
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
  return {
    id,
    name: text(slot.name),
    description: text(slot.description),
    imageUrl: modelImage(id, slot.icon_file),
    status: type === 'RVC' ? 'ready' : type === 'RESERVED_FOR_SAMPLE' ? 'pending' : type === 'BROKEN' ? 'broken' : 'unsupported',
    tags,
    settings: type === 'RVC' ? {
      supportsPitch: slot.is_f0 === true,
      hasIndex: text(slot.index_file).trim().length > 0,
      pitch: numeric(slot.pitch_shift),
      indexRatio: numeric(slot.index_ratio),
      pitchEstimator: text(slot.pitch_estimator) || null,
      embedder: text(slot.embedder) || null,
      chunkSeconds: numeric(slot.chunk_sec),
    } : null,
  };
}

function parseCatalog(slots: unknown, configuration: unknown): ModelCatalog {
  if (!Array.isArray(slots)) invalidResponse();
  const ids = new Set<number>();
  const models: ModelSummary[] = [];
  for (const value of slots) {
    const slot = object(value);
    if (!Number.isSafeInteger(slot.slot_index) || (slot.slot_index as number) < 0) invalidResponse();
    const id = slot.slot_index as number;
    if (ids.has(id)) invalidResponse();
    ids.add(id);
    if (slot.voice_changer_type !== null) models.push(parseModel(slot));
  }

  return {
    models: models.sort((a, b) => a.id - b.id),
    ...parseConfiguration(configuration),
  };
}

async function responseJson(response: Response, signal: AbortSignal): Promise<unknown> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new ApiError('http', response.status,
      typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message : undefined);
  }
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

const editFields: Record<keyof ConfigurationEdits, string> = {
  currentModelId: 'current_slot_index', inputMode: 'voice_changer_input_mode', passThrough: 'pass_through', recording: 'recording_started',
  inputDevice: 'audio_input_device_index', outputDevice: 'audio_output_device_index',
  monitorDevice: 'audio_monitor_device_index',
  inputDeviceRate: 'audio_input_device_sample_rate', outputDeviceRate: 'audio_output_device_sample_rate',
  monitorDeviceRate: 'audio_monitor_device_sample_rate',
  wasapiExclusive: 'wasapi_exclude_emabled',
  extraSeconds: 'extra_frame_sec',
  crossfadeSeconds: 'crossfade_sec',
  inputGain: 'audio_input_device_gain', outputGain: 'audio_output_device_gain',
  noiseGate: 'noise_gate',
  highPassEnabled: 'enable_high_pass_filter', lowPassEnabled: 'enable_low_pass_filter',
  highPassCutoff: 'high_pass_filter_cutoff', lowPassCutoff: 'low_pass_filter_cutoff',
};

const filterKeys = ['highPassEnabled', 'lowPassEnabled', 'highPassCutoff', 'lowPassCutoff'];
const liveKeys = ['inputGain', 'outputGain', 'noiseGate', 'passThrough', 'recording', ...filterKeys];

export async function readNativeActive(signal: AbortSignal): Promise<boolean> {
  const info = object(await getJson(`${nativeUrl}/information`, signal));
  if (typeof info.local_voice_changer_interface_active !== 'boolean') invalidResponse();
  return info.local_voice_changer_interface_active;
}

export async function updateConfiguration(edits: ConfigurationEdits, signal: AbortSignal): Promise<ConfirmedConfiguration> {
  // Topology changes are only allowed while stopped, including changes from other clients.
  if (Object.keys(edits).some(key => !liveKeys.includes(key)) && await readNativeActive(signal)) {
    throw new ApiError('active');
  }
  const config = object(await getJson(configurationUrl, signal));
  parseConfiguration(config);
  if (edits.recording === true && (config.pass_through !== false || !(await readNativeActive(signal)))) throw new ApiError('recording_unavailable');
  if (edits.passThrough === true && config.recording_started !== false) throw new ApiError('recording_unavailable');
  if (edits.recording !== undefined) {
    const info = object(await getJson('/api/voice-changer-manager/information', signal));
    const voice = object(info.voice_changer_information);
    if (typeof voice.recording_start_flag !== 'boolean' || voice.recording_start_flag !== config.recording_started) throw new ApiError('recording_unavailable');
    if (voice.recording_start_flag === edits.recording) throw new ApiError('recording_unavailable');
  }
  const changes = Object.entries(edits).map(([key, value]) => [editFields[key as keyof ConfigurationEdits], value] as const);
  if (changes.some(([field]) => !Object.hasOwn(config, field))) invalidResponse();
  if (Object.keys(edits).some(key => filterKeys.includes(key))) {
    const information = object(await getJson('/api/voice-changer-manager/information', signal));
    const voice = object(information.voice_changer_information);
    const high = edits.highPassCutoff ?? numeric(config.high_pass_filter_cutoff);
    const low = edits.lowPassCutoff ?? numeric(config.low_pass_filter_cutoff);
    const rates = [numeric(config.input_sample_rate), numeric(voice.input_sample_rate), numeric(voice.output_sample_rate)];
    if (!Number.isSafeInteger(voice.slot_index) || (voice.slot_index as number) < 0 || voice.slot_index !== config.current_slot_index
      || rates.some(rate => rate === null || rate <= 0) || high === null || low === null
      || high <= 0 || low <= 0 || high >= Math.min(low, rates[0]! * 0.45, rates[1]! * 0.45)) {
      throw new ApiError('invalid_filter');
    }
  }
  // PUT replaces the entire DTO. Retain all fields, including ones this UI does not understand.
  await responseJson(await fetch(configurationUrl, {
    method: 'PUT', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...config, ...Object.fromEntries(changes) }),
  }), signal);
  // The legacy endpoint returns null and may silently roll back a failed model switch.
  const confirmed = object(await getJson(configurationUrl, signal));
  const snapshot = parseConfiguration(confirmed);
  if (changes.some(([field, value]) => confirmed[field] !== value)) throw new ApiError('not_applied');
  if (edits.recording !== undefined) {
    const info = object(await getJson('/api/voice-changer-manager/information', signal));
    if (object(info.voice_changer_information).recording_start_flag !== edits.recording) throw new ApiError('not_applied');
  }
  return snapshot;
}

export async function operateNative(operation: 'start' | 'stop', signal: AbortSignal): Promise<boolean> {
  await responseJson(await fetch(`${nativeUrl}/operation/${operation}`, { method: 'POST', signal }), signal);
  const active = await readNativeActive(signal);
  if (active !== (operation === 'start')) throw new ApiError('not_applied');
  return active;
}

export async function organizeModels(order: number[], deleteSelected: boolean, signal: AbortSignal): Promise<void> {
  const response = await fetch('/api/slot-manager/operation/organize', {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ order, delete_selected: deleteSelected }),
  });
  await responseJson(response, signal);
}

export async function updateModelSettings(id: number, edits: ModelEdits, signal: AbortSignal): Promise<ModelSummary> {
  if (!Number.isSafeInteger(id) || id < 0) invalidResponse();
  if ((edits.pitchEstimator !== undefined || edits.chunkSeconds !== undefined) && await readNativeActive(signal)) throw new ApiError('active');
  const url = `/api/slot-manager/slots/${id}`;
  const slot = object(await getJson(url, signal));
  const model = parseModel(slot);
  if (model.id !== id || !model.settings) invalidResponse();
  const changes: Record<string, number | string> = {};
  if (edits.pitch !== undefined) {
    if (!model.settings.supportsPitch || model.settings.pitch === null || !Number.isInteger(edits.pitch) || edits.pitch < -24 || edits.pitch > 24) invalidResponse();
    changes.pitch_shift = edits.pitch;
  }
  if (edits.indexRatio !== undefined) {
    if (!model.settings.hasIndex || model.settings.indexRatio === null || !Number.isFinite(edits.indexRatio) || edits.indexRatio < 0 || edits.indexRatio > 1) invalidResponse();
    changes.index_ratio = edits.indexRatio;
  }
  if (edits.pitchEstimator !== undefined) {
    if (!model.settings.supportsPitch || !model.settings.pitchEstimator || !['rmvpe', 'fcpe'].includes(edits.pitchEstimator)) invalidResponse();
    changes.pitch_estimator = edits.pitchEstimator;
  }
  if (edits.chunkSeconds !== undefined) {
    if (model.settings.chunkSeconds === null || !Number.isFinite(edits.chunkSeconds) || edits.chunkSeconds < 0.05 || edits.chunkSeconds > 5) invalidResponse();
    changes.chunk_sec = edits.chunkSeconds;
  }
  // The endpoint consumes a complete RVCSlotInfo and uses its slot_index for persistence.
  await responseJson(await fetch(url, {
    method: 'PUT', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...slot, ...changes }),
  }), signal);
  const confirmed = object(await getJson(url, signal));
  const result = parseModel(confirmed);
  if (result.id !== id || !result.settings) invalidResponse();
  if (Object.entries(changes).some(([key, value]) => confirmed[key] !== value)) throw new ApiError('not_applied');
  if (edits.pitchEstimator !== undefined) {
    const info = object(await getJson('/api/voice-changer-manager/information', signal));
    const voice = object(info.voice_changer_information);
    const pipeline = object(voice.pipeline_info);
    const estimator = object(pipeline.pitch_estimator_info);
    if (voice.slot_index !== id || pipeline.slot_index !== id || estimator.pitch_estimator_type !== edits.pitchEstimator) {
      throw new ApiError('not_applied');
    }
  }
  return result;
}
