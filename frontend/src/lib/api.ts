import type { ModelCatalog, ModelSummary } from './catalog';
import { ApiError, type ApiErrorCode } from './api-error';
import type {
  ConfigurationEdits,
  ConfigurationSnapshot,
  ConfirmedConfiguration,
  ConfirmedSession,
  ModelEdits,
  SessionLastError,
  SessionRuntimeSnapshot,
  SessionSnapshotPayload,
  SessionStateSnapshot,
  SessionStatus,
} from './settings';
import type { AudioDevice, AudioDevices } from './audio-devices';

const settingsUrl = '/api/settings';
const sessionUrl = '/api/session';

export function websocketUrl(path: string): string {
  const url = new URL(path, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

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

function parseSettingsFields(config: Record<string, unknown>): ConfigurationSnapshot {
  const mode = config.input_mode ?? null;
  if (mode !== null && mode !== 'server' && mode !== 'client') invalidResponse();
  return {
    inputMode: mode,
    passThrough: null,
    recording: null,
    inputGain: numeric(config.input_gain),
    outputGain: numeric(config.output_gain),
    inputDevice: numeric(config.audio_input_device_index),
    outputDevice: numeric(config.audio_output_device_index),
    monitorDevice: numeric(config.audio_monitor_device_index),
    inputDeviceRate: numeric(config.audio_input_device_sample_rate),
    outputDeviceRate: numeric(config.audio_output_device_sample_rate),
    monitorDeviceRate: numeric(config.audio_monitor_device_sample_rate),
    gpuDevice: numeric(config.compute_device_id),
    wasapiExclusive: boolean(config.wasapi_exclusive_enabled),
    highPassEnabled: boolean(config.enable_high_pass_filter),
    highPassCutoff: numeric(config.high_pass_filter_cutoff),
    lowPassEnabled: boolean(config.enable_low_pass_filter),
    lowPassCutoff: numeric(config.low_pass_filter_cutoff),
    noiseGate: numeric(config.noise_gate),
    extraSeconds: numeric(config.extra_frame_sec),
    ioAnalysisEnabled: boolean(config.realtime_output_status_enabled),
    processAnalysisEnabled: boolean(config.realtime_process_status_enabled),
    performanceMonitorEnabled: boolean(config.enable_performance_monitor),
  };
}

function modelImage(id: string, hasIcon: boolean, iconRevision: number): string | null {
  if (!hasIcon) return null;
  return `/api/models/${encodeURIComponent(id)}/icon?v=${iconRevision}`;
}

function parseConfiguration(configuration: unknown, etag: string | null): ConfirmedConfiguration {
  const config = object(configuration);
  if (config.model_id !== undefined && config.model_id !== null && typeof config.model_id !== 'string') invalidResponse();
  const currentModelId = typeof config.model_id === 'string' && config.model_id.length > 0 ? config.model_id : null;
  return { currentModelId, settings: parseSettingsFields(config), etag };
}

function parseRuntimeSnapshot(raw: unknown): SessionRuntimeSnapshot {
  const snap = object(raw);
  if (typeof snap.model_id !== 'string' || !snap.model_id) invalidResponse();
  const base = parseSettingsFields(snap);
  const pitchEstimator = snap.pitch_estimator ?? null;
  if (pitchEstimator !== null && typeof pitchEstimator !== 'string') invalidResponse();
  return {
    ...base,
    modelId: snap.model_id,
    passThrough: boolean(snap.pass_through),
    recording: boolean(snap.recording),
    pitch: numeric(snap.pitch_shift),
    indexRatio: numeric(snap.index_ratio),
    pitchEstimator: pitchEstimator || null,
    chunkSeconds: numeric(snap.chunk_sec),
  };
}

function parseLastError(raw: unknown): SessionLastError | null {
  if (raw === undefined || raw === null) return null;
  const err = object(raw);
  if (typeof err.code !== 'string' || typeof err.message !== 'string') invalidResponse();
  const details = err.details === undefined || err.details === null ? {} : object(err.details);
  return { code: err.code, message: err.message, details };
}

function parseSessionState(raw: unknown): SessionStateSnapshot {
  const state = object(raw);
  const status = state.status;
  if (status !== 'stopped' && status !== 'starting' && status !== 'running') invalidResponse();
  const snapshot = state.snapshot === undefined || state.snapshot === null ? null : parseRuntimeSnapshot(state.snapshot);
  const lockedRaw = state.locked_fields ?? [];
  if (!Array.isArray(lockedRaw) || lockedRaw.some(item => typeof item !== 'string')) invalidResponse();
  return {
    status: status as SessionStatus,
    snapshot,
    lockedFields: lockedRaw as string[],
    inputSampleRate: numeric(state.input_sample_rate),
    outputSampleRate: numeric(state.output_sample_rate),
    monitorSampleRate: numeric(state.monitor_sample_rate),
    lastError: parseLastError(state.last_error),
  };
}

function parseModel(entry: Record<string, unknown>): ModelSummary {
  if (typeof entry.id !== 'string' || !entry.id.trim()) invalidResponse();
  const id = entry.id;
  if (typeof entry.name !== 'string') invalidResponse();
  if (
    typeof entry.supports_f0 !== 'boolean'
    || typeof entry.has_index !== 'boolean'
    || typeof entry.has_icon !== 'boolean'
  ) invalidResponse();
  const iconRevision = Number.isSafeInteger(entry.icon_revision) && (entry.icon_revision as number) >= 0
    ? (entry.icon_revision as number) : 0;
  const version = text(entry.version);
  const embedder = text(entry.embedder);
  const tags = [
    'RVC',
    version ? `onnx ${version}` : 'onnx',
    entry.supports_f0 ? 'f0' : 'non-f0',
    ...(embedder ? [embedder] : []),
  ];
  return {
    id,
    name: entry.name,
    imageUrl: modelImage(id, entry.has_icon, iconRevision),
    status: 'ready',
    tags,
    settings: {
      supportsPitch: entry.supports_f0,
      hasIndex: entry.has_index,
      pitch: numeric(entry.pitch_shift),
      indexRatio: numeric(entry.index_ratio),
      pitchEstimator: text(entry.pitch_estimator) || null,
      embedder: embedder || null,
      chunkSeconds: numeric(entry.chunk_sec),
    },
  };
}

function parseCatalog(
  modelsPayload: unknown,
  settingsResult: { data: unknown; etag: string | null },
): ModelCatalog {
  if (!Array.isArray(modelsPayload)) invalidResponse();
  const ids = new Set<string>();
  const models: ModelSummary[] = [];
  for (const value of modelsPayload) {
    const model = parseModel(object(value));
    if (ids.has(model.id)) invalidResponse();
    ids.add(model.id);
    models.push(model);
  }
  const confirmed = parseConfiguration(settingsResult.data, settingsResult.etag);
  return {
    models,
    currentModelId: confirmed.currentModelId,
    settings: confirmed.settings,
    settingsEtag: confirmed.etag,
  };
}

function parseErrorDetail(body: unknown): {
  detail?: string;
  backendCode?: string;
  details?: Record<string, unknown>;
} {
  if (!body || typeof body !== 'object') return {};
  const record = body as Record<string, unknown>;
  if (typeof record.code === 'string' || typeof record.message === 'string') {
    const details = record.details && typeof record.details === 'object' && !Array.isArray(record.details)
      ? (record.details as Record<string, unknown>) : undefined;
    return {
      detail: typeof record.message === 'string' ? record.message : undefined,
      backendCode: typeof record.code === 'string' ? record.code : undefined,
      details,
    };
  }
  const detail = record.detail;
  if (typeof detail === 'string') {
    const nested = parseJsonText(detail);
    if (nested && typeof nested === 'object') {
      const obj = nested as Record<string, unknown>;
      return {
        detail: typeof obj.message === 'string' ? obj.message : detail,
        backendCode: typeof obj.code === 'string' ? obj.code : undefined,
      };
    }
    return { detail };
  }
  if (detail && typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    return {
      detail: typeof obj.message === 'string' ? obj.message : undefined,
      backendCode: typeof obj.code === 'string' ? obj.code : undefined,
    };
  }
  return {};
}

const backendErrorCodeMap: Record<string, ApiErrorCode> = {
  session_starting: 'starting',
  session_active: 'active',
  session_rebuild_required: 'rebuild_required',
  model_in_use: 'model_in_use',
  model_not_found: 'model_not_found',
  invalid_compute_device: 'invalid_compute_device',
  invalid_audio_device: 'invalid_audio_device',
  invalid_filter_cutoff: 'invalid_filter',
  etag_mismatch: 'etag_mismatch',
};

function apiErrorFromHttp(status: number, body: unknown): ApiError {
  const { detail, backendCode, details } = parseErrorDetail(body);
  const code = (backendCode && backendErrorCodeMap[backendCode]) || 'http';
  return new ApiError(code, status, detail, backendCode, details);
}

function parseJsonText(raw: string): unknown {
  try { return JSON.parse(raw); }
  catch { return undefined; }
}

async function responseJsonWithEtag(
  response: Response,
  signal: AbortSignal,
): Promise<{ data: unknown; etag: string | null }> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw apiErrorFromHttp(response.status, body);
  }
  const etag = response.headers.get('etag');
  try {
    return { data: await response.json(), etag };
  } catch (error) {
    if (signal.aborted) throw error;
    invalidResponse();
  }
}

async function responseJson(response: Response, signal: AbortSignal): Promise<unknown> {
  return (await responseJsonWithEtag(response, signal)).data;
}

export interface MultipartOptions {
  method: 'POST' | 'PUT' | 'PATCH';
  url: string;
  body: FormData;
  signal: AbortSignal;
  ifMatch?: string | null;
  onProgress?: (loaded: number, total?: number) => void;
  onUploaded?: () => void;
}

export function sendMultipart({ method, url, body, signal, ifMatch, onProgress, onUploaded }: MultipartOptions): Promise<unknown> {
  if (signal.aborted) return Promise.reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let uploaded = false;
    const finishUploaded = () => {
      if (uploaded) return;
      uploaded = true;
      onUploaded?.();
    };
    const onAbort = () => xhr.abort();
    const cleanup = () => signal.removeEventListener('abort', onAbort);
    signal.addEventListener('abort', onAbort, { once: true });

    xhr.open(method, url);
    if (ifMatch) xhr.setRequestHeader('If-Match', ifMatch);
    xhr.responseType = 'text';

    xhr.upload.onprogress = event => {
      onProgress?.(event.loaded, event.lengthComputable ? event.total : undefined);
      if (event.lengthComputable && event.loaded >= event.total) finishUploaded();
    };
    xhr.upload.onload = finishUploaded;

    xhr.onload = () => {
      cleanup();
      finishUploaded();
      const parsed = parseJsonText(xhr.responseText);
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(apiErrorFromHttp(xhr.status, parsed));
        return;
      }
      if (parsed === undefined) {
        reject(new ApiError('invalid_response'));
        return;
      }
      resolve(parsed);
    };
    xhr.onerror = () => {
      cleanup();
      reject(new ApiError('network'));
    };
    xhr.onabort = () => {
      cleanup();
      reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    };

    xhr.send(body);
  });
}

async function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  return responseJson(await fetch(path, { method: 'GET', signal, cache: 'no-store' }), signal);
}

async function getJsonWithEtag(path: string, signal: AbortSignal): Promise<{ data: unknown; etag: string | null }> {
  return responseJsonWithEtag(await fetch(path, { method: 'GET', signal, cache: 'no-store' }), signal);
}

function jsonHeaders(ifMatch?: string | null): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ifMatch) headers['If-Match'] = ifMatch;
  return headers;
}

export async function loadModelCatalog(signal: AbortSignal): Promise<ModelCatalog> {
  const [models, settingsResult] = await Promise.all([
    getJson('/api/models', signal),
    getJsonWithEtag(settingsUrl, signal),
  ]);
  return parseCatalog(models, settingsResult);
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

export async function loadAudioDevices(signal: AbortSignal, rescan = false): Promise<AudioDevices> {
  const payload = rescan
    ? await responseJson(await fetch('/api/devices/audio/reload', { method: 'POST', signal, cache: 'no-store' }), signal)
    : await getJson('/api/devices/audio', signal);
  const response = object(payload);
  return { input: parseDevices(response.inputs), output: parseDevices(response.outputs) };
}

export interface ComputeDevice { id: number; name: string }

export async function loadComputeDevices(signal: AbortSignal): Promise<ComputeDevice[]> {
  const value = await getJson('/api/devices/compute', signal);
  if (!Array.isArray(value)) invalidResponse();
  const ids = new Set<number>();
  return value.map(item => {
    const device = object(item);
    if (!Number.isSafeInteger(device.id) || (device.id as number) < 0 || ids.has(device.id as number)) invalidResponse();
    if (typeof device.name !== 'string' || !device.name.trim()) invalidResponse();
    const id = device.id as number;
    ids.add(id);
    return { id, name: device.name };
  });
}

export async function autoSelectComputeDevice(signal: AbortSignal): Promise<number> {
  const payload = object(await responseJson(await fetch('/api/devices/compute/auto-select', {
    method: 'POST', signal, cache: 'no-store',
  }), signal));
  const id = numeric(payload.compute_device_id);
  if (id === null) invalidResponse();
  return id;
}

const settingsEditFields: Partial<Record<keyof ConfigurationEdits, string>> = {
  currentModelId: 'model_id',
  inputMode: 'input_mode',
  inputDevice: 'audio_input_device_index',
  outputDevice: 'audio_output_device_index',
  monitorDevice: 'audio_monitor_device_index',
  inputDeviceRate: 'audio_input_device_sample_rate',
  outputDeviceRate: 'audio_output_device_sample_rate',
  monitorDeviceRate: 'audio_monitor_device_sample_rate',
  gpuDevice: 'compute_device_id',
  wasapiExclusive: 'wasapi_exclusive_enabled',
  extraSeconds: 'extra_frame_sec',
  ioAnalysisEnabled: 'realtime_output_status_enabled',
  processAnalysisEnabled: 'realtime_process_status_enabled',
  performanceMonitorEnabled: 'enable_performance_monitor',
  inputGain: 'input_gain',
  outputGain: 'output_gain',
  noiseGate: 'noise_gate',
  highPassEnabled: 'enable_high_pass_filter',
  lowPassEnabled: 'enable_low_pass_filter',
  highPassCutoff: 'high_pass_filter_cutoff',
  lowPassCutoff: 'low_pass_filter_cutoff',
};

const filterKeys = ['highPassEnabled', 'lowPassEnabled', 'highPassCutoff', 'lowPassCutoff'];

export async function readAudioSampleRates(signal: AbortSignal): Promise<{ input: number | null; output: number | null }> {
  const { session } = await readSessionState(signal);
  return {
    input: session.inputSampleRate !== null && session.inputSampleRate > 0 ? session.inputSampleRate : null,
    output: session.outputSampleRate !== null && session.outputSampleRate > 0 ? session.outputSampleRate : null,
  };
}

export async function readSessionState(signal: AbortSignal): Promise<ConfirmedSession> {
  const { data, etag } = await getJsonWithEtag(sessionUrl, signal);
  return { session: parseSessionState(data), etag };
}

export async function putSession(
  payload: SessionSnapshotPayload,
  signal: AbortSignal,
  ifMatch?: string | null,
): Promise<ConfirmedSession> {
  const response = await fetch(sessionUrl, {
    method: 'PUT',
    signal,
    headers: jsonHeaders(ifMatch),
    body: JSON.stringify(payload),
  });
  const { data, etag } = await responseJsonWithEtag(response, signal);
  return { session: parseSessionState(data), etag };
}

export async function stopSession(signal: AbortSignal, ifMatch?: string | null): Promise<ConfirmedSession> {
  const headers: Record<string, string> = {};
  if (ifMatch) headers['If-Match'] = ifMatch;
  const response = await fetch(sessionUrl, { method: 'DELETE', signal, headers });
  const { data, etag } = await responseJsonWithEtag(response, signal);
  return { session: parseSessionState(data), etag };
}

export function validateFilterParameters(
  high: number | null,
  low: number | null,
  highEnabled: boolean,
  lowEnabled: boolean,
  inputRate: number | null,
): void {
  if (high === null || low === null || high < 1 || low < 1 || high > 24000 || low > 24000 || high >= low) {
    throw new ApiError('invalid_filter');
  }
  if (inputRate !== null && inputRate > 0) {
    const nyquist = inputRate / 2;
    if ((highEnabled && high >= nyquist) || (lowEnabled && low >= nyquist)) {
      throw new ApiError('invalid_filter');
    }
  }
}

export async function updateSettings(
  edits: ConfigurationEdits,
  signal: AbortSignal,
  sampleRates?: { input: number | null } | null,
): Promise<ConfirmedConfiguration> {
  const entries = Object.entries(edits)
    .map(([key, value]) => [key, settingsEditFields[key as keyof ConfigurationEdits], value] as const)
    .filter((entry): entry is [string, string, unknown] => entry[1] !== undefined);
  if (entries.length === 0) invalidResponse();

  for (let attempt = 0; attempt < 2; attempt++) {
    const { data, etag } = await getJsonWithEtag(settingsUrl, signal);
    const config = object(data);
    parseSettingsFields(config);
    const changes = entries.map(([, field, value]) => [field, value] as const);
    if (changes.some(([field]) => !Object.hasOwn(config, field))) invalidResponse();

    if (Object.keys(edits).some(key => filterKeys.includes(key))) {
      const high = edits.highPassCutoff ?? numeric(config.high_pass_filter_cutoff);
      const low = edits.lowPassCutoff ?? numeric(config.low_pass_filter_cutoff);
      const highEnabled = edits.highPassEnabled ?? boolean(config.enable_high_pass_filter) ?? false;
      const lowEnabled = edits.lowPassEnabled ?? boolean(config.enable_low_pass_filter) ?? false;
      validateFilterParameters(high, low, highEnabled, lowEnabled, sampleRates?.input ?? null);
    }

    try {
      const { data: savedRaw, etag: nextEtag } = await responseJsonWithEtag(await fetch(settingsUrl, {
        method: 'PUT',
        signal,
        headers: jsonHeaders(etag),
        body: JSON.stringify({ ...config, ...Object.fromEntries(changes) }),
      }), signal);
      const confirmedObj = object(savedRaw);
      const confirmed = parseConfiguration(confirmedObj, nextEtag);
      if (changes.some(([field, value]) => confirmedObj[field] !== value)) throw new ApiError('not_applied');
      return confirmed;
    } catch (error) {
      if (attempt === 0 && error instanceof ApiError && error.code === 'etag_mismatch') continue;
      throw error;
    }
  }
  invalidResponse();
}

export async function organizeModels(order: string[], signal: AbortSignal): Promise<void> {
  const response = await fetch('/api/models/order', {
    method: 'PUT', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_ids: order }),
  });
  await responseJson(response, signal);
}

export async function deleteModel(id: string, signal: AbortSignal): Promise<void> {
  if (!id.trim()) invalidResponse();
  const response = await fetch(`/api/models/${encodeURIComponent(id)}`, { method: 'DELETE', signal });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw apiErrorFromHttp(response.status, body);
  }
}

export async function readModel(id: string, signal: AbortSignal): Promise<ModelSummary> {
  if (!id.trim()) invalidResponse();
  const model = parseModel(object(await getJson(`/api/models/${encodeURIComponent(id)}`, signal)));
  if (model.id !== id || model.status !== 'ready') invalidResponse();
  return model;
}

export async function updateModelInfo(
  id: string,
  updates: { name?: string; icon?: File | null },
  signal: AbortSignal,
): Promise<ModelSummary> {
  if (!id.trim()) invalidResponse();
  let latestRaw: Record<string, unknown> | null = null;
  if (updates.name !== undefined) {
    latestRaw = object(await responseJson(await fetch(`/api/models/${encodeURIComponent(id)}`, {
      method: 'PUT',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: updates.name }),
    }), signal));
  }
  if (updates.icon) {
    const form = new FormData();
    form.append('icon_file', updates.icon, updates.icon.name);
    latestRaw = object(await sendMultipart({
      method: 'PUT',
      url: `/api/models/${encodeURIComponent(id)}/icon`,
      body: form,
      signal,
    }));
  }
  if (!latestRaw) invalidResponse();
  const model = parseModel(latestRaw);
  if (model.id !== id) invalidResponse();
  if (updates.name !== undefined && model.name !== updates.name.trim()) throw new ApiError('not_applied');
  if (updates.icon && !model.imageUrl) throw new ApiError('not_applied');
  return model;
}

export async function updateModelSettings(id: string, edits: ModelEdits, signal: AbortSignal): Promise<ModelSummary> {
  if (!id.trim()) invalidResponse();
  const url = `/api/models/${encodeURIComponent(id)}`;
  for (let attempt = 0; attempt < 2; attempt++) {
    const { data, etag } = await getJsonWithEtag(url, signal);
    const raw = object(data);
    const model = parseModel(raw);
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
    try {
      const confirmed = object(await responseJson(await fetch(url, {
        method: 'PUT',
        signal,
        headers: jsonHeaders(etag),
        body: JSON.stringify(changes),
      }), signal));
      const result = parseModel(confirmed);
      if (result.id !== id || !result.settings) invalidResponse();
      if (Object.entries(changes).some(([key, value]) => confirmed[key] !== value)) throw new ApiError('not_applied');
      return result;
    } catch (error) {
      if (attempt === 0 && error instanceof ApiError && error.code === 'etag_mismatch') continue;
      throw error;
    }
  }
  invalidResponse();
}
