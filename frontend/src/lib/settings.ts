export interface ConfigurationSnapshot {
  inputMode: 'server' | 'client' | null;
  passThrough: boolean | null;
  recording: boolean | null;
  inputGain: number | null;
  outputGain: number | null;
  monitorGain: number | null;
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
  crossfadeSeconds: number | null;
  ioAnalysisEnabled: boolean | null;
  ioAnalysisInterval: number | null;
  processAnalysisEnabled: boolean | null;
  processAnalysisInterval: number | null;
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
  pitchEstimator?: 'rmvpe' | 'fcpe';
  chunkSeconds?: number;
}

// Only these fields can be changed by the native-audio UI.
export interface ConfigurationEdits {
  currentModelId?: number;
  inputMode?: 'server';
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
  crossfadeSeconds?: number;
  inputGain?: number;
  outputGain?: number;
  noiseGate?: number;
  highPassEnabled?: boolean;
  lowPassEnabled?: boolean;
  highPassCutoff?: number;
  lowPassCutoff?: number;
}

export interface ConfirmedConfiguration {
  currentModelId: number | null;
  settings: ConfigurationSnapshot;
}

export function displayNumber(value: number | null | undefined, unit = ''): string {
  return value === null || value === undefined ? '—' : `${value}${unit}`;
}
