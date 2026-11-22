export type SessionStatus = 'stopped' | 'starting' | 'running';
export type InputMode = 'server' | 'client';
export type PitchEstimator = 'rmvpe' | 'fcpe';

export interface ConfigurationSnapshot {
  inputMode: InputMode | null;
  passThrough: boolean | null;
  recording: boolean | null;
  inputGain: number | null;
  outputGain: number | null;
  inputDevice: number | null;
  outputDevice: number | null;
  monitorDevice: number | null;
  inputDeviceRate: number | null;
  outputDeviceRate: number | null;
  monitorDeviceRate: number | null;
  gpuDevice: number | null;
  wasapiExclusive: boolean | null;
  highPassEnabled: boolean | null;
  highPassCutoff: number | null;
  lowPassEnabled: boolean | null;
  lowPassCutoff: number | null;
  noiseGate: number | null;
  extraSeconds: number | null;
  ioAnalysisEnabled: boolean | null;
  processAnalysisEnabled: boolean | null;
  performanceMonitorEnabled: boolean | null;
}

export interface ModelSettingsSnapshot {
  supportsPitch: boolean;
  hasIndex: boolean;
  pitch: number | null;
  indexRatio: number | null;
  pitchEstimator: string | null;
  embedder: string | null;
  chunkSeconds: number | null;
}

export interface ModelEdits {
  pitch?: number;
  indexRatio?: number;
  pitchEstimator?: PitchEstimator;
  chunkSeconds?: number;
}

export interface ConfigurationEdits {
  currentModelId?: string;
  inputMode?: InputMode;
  passThrough?: boolean;
  recording?: boolean;
  inputDevice?: number;
  outputDevice?: number;
  monitorDevice?: number;
  inputDeviceRate?: number;
  outputDeviceRate?: number;
  monitorDeviceRate?: number;
  gpuDevice?: number;
  wasapiExclusive?: boolean;
  extraSeconds?: number;
  ioAnalysisEnabled?: boolean;
  processAnalysisEnabled?: boolean;
  performanceMonitorEnabled?: boolean;
  inputGain?: number;
  outputGain?: number;
  noiseGate?: number;
  highPassEnabled?: boolean;
  lowPassEnabled?: boolean;
  highPassCutoff?: number;
  lowPassCutoff?: number;
}

export interface SessionLastError {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface SessionRuntimeSnapshot extends ConfigurationSnapshot {
  modelId: string;
  pitch: number | null;
  indexRatio: number | null;
  pitchEstimator: string | null;
  chunkSeconds: number | null;
}

export interface SessionStateSnapshot {
  status: SessionStatus;
  snapshot: SessionRuntimeSnapshot | null;
  lockedFields: string[];
  inputSampleRate: number | null;
  outputSampleRate: number | null;
  monitorSampleRate: number | null;
  lastError: SessionLastError | null;
}

export interface SessionSnapshotPayload {
  model_id: string;
  pitch_shift: number;
  index_ratio: number;
  chunk_sec: number;
  pitch_estimator: PitchEstimator;
  extra_frame_sec: number;
  compute_device_id: number;
  input_mode: InputMode;
  audio_input_device_index: number;
  audio_output_device_index: number;
  audio_monitor_device_index: number;
  audio_input_device_sample_rate: number;
  audio_output_device_sample_rate: number;
  audio_monitor_device_sample_rate: number;
  wasapi_exclusive_enabled: boolean;
  input_gain: number;
  output_gain: number;
  enable_high_pass_filter: boolean;
  high_pass_filter_cutoff: number;
  enable_low_pass_filter: boolean;
  low_pass_filter_cutoff: number;
  noise_gate: number;
  pass_through: boolean;
  recording: boolean;
  enable_performance_monitor: boolean;
  realtime_process_status_enabled: boolean;
  realtime_output_status_enabled: boolean;
}

export interface ConfirmedConfiguration {
  currentModelId: string | null;
  settings: ConfigurationSnapshot;
  etag: string | null;
}

export interface ConfirmedSession {
  session: SessionStateSnapshot;
  etag: string | null;
}

export function displayNumber(value: number | null | undefined, unit = ''): string {
  return value === null || value === undefined ? '—' : `${value}${unit}`;
}
