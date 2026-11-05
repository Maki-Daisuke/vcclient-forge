export interface ConfigurationSnapshot {
  inputMode: 'server' | 'client' | null;
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
  ioAnalysisEnabled: boolean | null;
  ioAnalysisInterval: number | null;
  processAnalysisEnabled: boolean | null;
  processAnalysisInterval: number | null;
}

export interface ModelSettingsSnapshot {
  pitch: number | null;
  indexRatio: number | null;
  pitchEstimator: string | null;
  embedder: string | null;
  chunkSeconds: number | null;
}

export function displayNumber(value: number | null | undefined, unit = ''): string {
  return value === null || value === undefined ? '—' : `${value}${unit}`;
}
