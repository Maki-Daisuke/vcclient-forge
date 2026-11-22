import { getContext, setContext } from 'svelte';
import {
  deleteModel,
  loadAudioDevices,
  organizeModels,
  putSession,
  readModel,
  readSessionState,
  stopSession,
  updateModelInfo,
  updateModelSettings,
  updateSettings,
  validateFilterParameters,
} from './api';
import { ClientAudio } from './client-audio.svelte';
import { ApiError } from './api-error';
import { importModel } from './model-upload';
import type { ModelCatalogState } from './catalog.svelte';
import type {
  ConfigurationEdits,
  ConfigurationSnapshot,
  ModelEdits,
  PitchEstimator,
  SessionLastError,
  SessionSnapshotPayload,
  SessionStateSnapshot,
} from './settings';

const contextKey = Symbol('native-session');
const updateIntervalMs = 100;
const startupPollIntervalMs = 100;
const startupTimeoutMs = 180_000;
type PendingWrite =
  | { kind: 'configuration'; edits: ConfigurationEdits }
  | { kind: 'model'; id: string; edits: ModelEdits };
type DeviceKey = 'inputDevice' | 'outputDevice' | 'monitorDevice';
const stagedKeys: (keyof ConfigurationEdits)[] = [
  'currentModelId',
  'inputMode',
  'inputDevice',
  'outputDevice',
  'monitorDevice',
  'inputDeviceRate',
  'outputDeviceRate',
  'monitorDeviceRate',
  'gpuDevice',
  'extraSeconds',
];

function mapLastErrorToApiError(lastError: SessionLastError): ApiError {
  switch (lastError.code) {
    case 'invalid_compute_device':
      return new ApiError('invalid_compute_device', undefined, lastError.message, lastError.code, lastError.details);
    case 'invalid_audio_device':
      return new ApiError('invalid_audio_device', undefined, lastError.message, lastError.code, lastError.details);
    case 'model_not_found':
      return new ApiError('model_not_found', undefined, lastError.message, lastError.code, lastError.details);
    case 'invalid_filter_cutoff':
      return new ApiError('invalid_filter', undefined, lastError.message, lastError.code, lastError.details);
    case 'session_starting':
      return new ApiError('starting', undefined, lastError.message, lastError.code, lastError.details);
    default:
      return new ApiError('session_start_failed', undefined, lastError.message, lastError.code, lastError.details);
  }
}

export interface SessionOverrideEdits extends Partial<ConfigurationEdits & ModelEdits> {}

function buildSessionPayload(
  base: ConfigurationSnapshot,
  modelId: string,
  modelSettings: NonNullable<ModelCatalogState['currentModel']>['settings'] & object,
  overrides: SessionOverrideEdits,
  recording: boolean,
): SessionSnapshotPayload {
  const inputMode = overrides.inputMode ?? base.inputMode;
  const computeDeviceId = overrides.gpuDevice ?? base.gpuDevice;
  const extraSeconds = overrides.extraSeconds ?? base.extraSeconds;
  const inputGain = overrides.inputGain ?? base.inputGain;
  const outputGain = overrides.outputGain ?? base.outputGain;
  const highPassEnabled = overrides.highPassEnabled ?? base.highPassEnabled;
  const highPassCutoff = overrides.highPassCutoff ?? base.highPassCutoff;
  const lowPassEnabled = overrides.lowPassEnabled ?? base.lowPassEnabled;
  const lowPassCutoff = overrides.lowPassCutoff ?? base.lowPassCutoff;
  const noiseGate = overrides.noiseGate ?? base.noiseGate;
  const perfEnabled = overrides.performanceMonitorEnabled ?? base.performanceMonitorEnabled;
  const procEnabled = overrides.processAnalysisEnabled ?? base.processAnalysisEnabled;
  const ioEnabled = overrides.ioAnalysisEnabled ?? base.ioAnalysisEnabled;
  const pitch = overrides.pitch ?? modelSettings.pitch;
  const indexRatio = overrides.indexRatio ?? modelSettings.indexRatio;
  const chunkSec = overrides.chunkSeconds ?? modelSettings.chunkSeconds;
  const estimator = (overrides.pitchEstimator ?? modelSettings.pitchEstimator) as PitchEstimator | null;

  if (
    inputMode === null
    || computeDeviceId === null
    || extraSeconds === null
    || inputGain === null
    || outputGain === null
    || highPassEnabled === null
    || highPassCutoff === null
    || lowPassEnabled === null
    || lowPassCutoff === null
    || noiseGate === null
    || perfEnabled === null
    || procEnabled === null
    || ioEnabled === null
    || pitch === null
    || indexRatio === null
    || chunkSec === null
    || (estimator !== 'rmvpe' && estimator !== 'fcpe')
  ) {
    throw new ApiError('invalid_response');
  }

  return {
    model_id: modelId,
    pitch_shift: pitch,
    index_ratio: indexRatio,
    chunk_sec: chunkSec,
    pitch_estimator: estimator,
    extra_frame_sec: extraSeconds,
    compute_device_id: computeDeviceId,
    input_mode: inputMode,
    audio_input_device_index: overrides.inputDevice ?? base.inputDevice ?? -1,
    audio_output_device_index: overrides.outputDevice ?? base.outputDevice ?? -1,
    audio_monitor_device_index: overrides.monitorDevice ?? base.monitorDevice ?? -1,
    audio_input_device_sample_rate: overrides.inputDeviceRate ?? base.inputDeviceRate ?? -1,
    audio_output_device_sample_rate: overrides.outputDeviceRate ?? base.outputDeviceRate ?? -1,
    audio_monitor_device_sample_rate: overrides.monitorDeviceRate ?? base.monitorDeviceRate ?? -1,
    wasapi_exclusive_enabled: overrides.wasapiExclusive ?? base.wasapiExclusive ?? false,
    input_gain: inputGain,
    output_gain: outputGain,
    enable_high_pass_filter: highPassEnabled,
    high_pass_filter_cutoff: highPassCutoff,
    enable_low_pass_filter: lowPassEnabled,
    low_pass_filter_cutoff: lowPassCutoff,
    noise_gate: noiseGate,
    pass_through: overrides.passThrough ?? base.passThrough ?? false,
    recording,
    enable_performance_monitor: perfEnabled,
    realtime_process_status_enabled: procEnabled,
    realtime_output_status_enabled: ioEnabled,
  };
}

export class NativeSession {
  readonly clientAudio = new ClientAudio();
  sessionState = $state<SessionStateSnapshot | null>(null);
  sessionEtag = $state<string | null>(null);
  draft = $state<ConfigurationEdits>({});
  modelDraft = $state<{ id: string; edits: ModelEdits } | null>(null);
  stagedConfiguration = $state<ConfigurationEdits>({});
  stagedModels = $state<Record<string, ModelEdits>>({});
  isSaving = $state(false);
  saved = $state(false);
  error = $state<ApiError | null>(null);
  active = $state<boolean | null>(null);
  statusError = $state(false);
  recordingCompleted = $state<Blob | null>(null);
  recordingNotice = $state<'empty' | 'download_failed' | 'superseded' | null>(null);
  recordingArmed = $state(false);
  uploadStatus = $state<'idle' | 'uploading' | 'registering' | 'success' | 'refresh_failed' | 'error' | 'uncertain'>('idle');
  uploadError = $state<ApiError | null>(null);
  uploadBytes = $state(0);
  uploadTotal = $state(0);
  operation = $state<'start' | 'stop' | null>(null);
  warmingUp = $state(false);
  organizing = $state(false);
  modelInfoSaving = $state(false);
  modelInfoError = $state<ApiError | null>(null);
  modelOperationError = $state<ApiError | null>(null);
  operationError = $state<ApiError | null>(null);
  deviceRescanning = $state(false);
  deviceRescanError = $state(false);
  devicesNeedingSelection = $state<DeviceKey[]>([]);
  private timer: ReturnType<typeof setTimeout> | undefined;
  private poll: ReturnType<typeof setTimeout> | undefined;
  private flight: Promise<void> | null = null;
  private requests = new Set<AbortController>();
  private lastStarted = -Infinity;
  private nextWrite: PendingWrite['kind'] = 'configuration';
  private lastEnabledNoiseGate = -60;
  private urgent = false;
  private statusVersion = 0;
  private reconnectVersion = 0;
  private reconnecting = false;
  private disposed = false;

  constructor(readonly catalog: ModelCatalogState) {}

  get starting() {
    return this.sessionState?.status === 'starting';
  }

  get settings(): ConfigurationSnapshot | null {
    const persisted = this.catalog.settings;
    if (!persisted) return null;
    const sessionSnap = this.sessionState?.status !== 'stopped' ? this.sessionState?.snapshot : null;
    const base: ConfigurationSnapshot = sessionSnap
      ? { ...persisted, ...sessionSnap }
      : { ...persisted, passThrough: false, recording: false };
    return {
      ...base,
      ...(this.active !== true ? this.stagedConfiguration : {}),
      ...this.draft,
    };
  }

  get currentModelId() {
    if (this.active === true || this.starting) {
      return this.sessionState?.snapshot?.modelId ?? this.catalog.currentModelId;
    }
    return this.stagedConfiguration.currentModelId ?? this.draft.currentModelId ?? this.catalog.currentModelId;
  }

  get currentModel() {
    return this.catalog.models.find(model => model.id === this.currentModelId) ?? null;
  }

  get modelSettings() {
    const model = this.currentModel;
    if (!model?.settings) return null;
    const snap = this.sessionState?.status !== 'stopped' ? this.sessionState?.snapshot : null;
    const liveOverrides: ModelEdits = snap && snap.modelId === model.id
      ? {
          ...(snap.pitch !== null ? { pitch: snap.pitch } : {}),
          ...(snap.indexRatio !== null ? { indexRatio: snap.indexRatio } : {}),
          ...(snap.pitchEstimator === 'rmvpe' || snap.pitchEstimator === 'fcpe'
            ? { pitchEstimator: snap.pitchEstimator } : {}),
          ...(snap.chunkSeconds !== null ? { chunkSeconds: snap.chunkSeconds } : {}),
        }
      : {};
    return {
      ...model.settings,
      ...liveOverrides,
      ...(this.active !== true ? this.stagedModels[model.id] : undefined),
      ...(this.modelDraft?.id === model.id ? this.modelDraft.edits : {}),
    };
  }

  get dirty() { return Object.keys(this.draft).length > 0 || this.modelDraft !== null; }
  get importing() { return this.uploadStatus === 'uploading' || this.uploadStatus === 'registering'; }
  get canReload() {
    return !this.deviceRescanning && !this.modelInfoSaving && !this.organizing && !this.importing
      && !this.isSaving && !this.operation && !this.starting && !this.dirty && this.catalog.state.status !== 'loading';
  }
  get canConfigure() {
    return this.catalog.state.status === 'ready' && this.active === false && !this.starting
      && !this.deviceRescanning && !this.modelInfoSaving && !this.organizing && !this.importing
      && !this.operation && !this.isSaving && !this.dirty;
  }
  get canOrganizeModels() {
    return this.canConfigure && this.stagedConfiguration.currentModelId === undefined && Object.keys(this.stagedModels).length === 0;
  }
  get canDeleteModel() { return this.canConfigure && this.currentModel?.status === 'ready'; }
  get canAdjustGain() {
    return this.catalog.state.status === 'ready' && this.settings?.inputMode != null && !this.starting
      && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation;
  }
  get canAdjustNoiseGate() {
    return this.catalog.state.status === 'ready' && this.settings?.inputMode != null && !this.starting
      && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation;
  }
  get canAdjustModel() {
    return this.catalog.state.status === 'ready' && !this.starting && !this.modelInfoSaving && !this.organizing
      && !this.importing && !this.operation && this.currentModel?.status === 'ready'
      && this.draft.currentModelId === undefined
      && (this.modelDraft === null || this.modelDraft.id === this.currentModelId);
  }
  get canAdjustFilter() {
    return this.canAdjustNoiseGate && this.currentModel?.status === 'ready' && this.draft.currentModelId === undefined;
  }

  get startBlockReason() {
    if (this.importing || this.organizing || this.modelInfoSaving || this.deviceRescanning) return 'saving';
    if (this.operation || this.starting) return 'operation';
    if (this.catalog.state.status === 'loading') return 'loading';
    if (this.catalog.state.status === 'error') return 'load_error';
    if (this.active === null) return 'unknown';
    if (this.active) return 'running';
    if (this.error) return 'save_error';
    if (this.isSaving || this.dirty) return 'saving';
    const settings = this.settings!;
    if (!settings.inputMode) return 'mode';
    if (settings.inputMode === 'client') return this.currentModel?.status === 'ready' ? null : 'model';
    const devices = this.catalog.deviceState;
    if (devices.status === 'loading') return 'devices_loading';
    if (devices.status === 'error') return 'devices_error';
    if (this.devicesNeedingSelection.length) return 'devices_changed';
    if (!devices.devices.input.some(device => device.id === settings.inputDevice)) return 'input';
    if (!devices.devices.output.some(device => device.id === settings.outputDevice)) return 'output';
    if (settings.monitorDevice !== -1 && !devices.devices.output.some(device => device.id === settings.monitorDevice)) return 'monitor';
    if (this.currentModel?.status !== 'ready') return 'model';
    return null;
  }
  get canStart() { return this.startBlockReason === null; }
  get canStop() { return (this.active !== false || this.statusError) && !this.operation && !this.starting; }

  async mount() {
    await this.reload();
    if (this.settings?.inputMode === 'client') await this.clientAudio.refreshDevices().catch(() => {});
    this.schedulePoll();
    if (this.sessionState?.status === 'running') void this.reconnectClientAudio(this.sessionState);
  }

  private applySessionConfirmed(confirmed: { session: SessionStateSnapshot; etag: string | null }) {
    this.sessionState = confirmed.session;
    this.sessionEtag = confirmed.etag;
    this.syncFromSessionState(confirmed.session);
  }

  private syncFromSessionState(session: SessionStateSnapshot | null) {
    if (!session) {
      this.active = null;
      this.statusError = true;
      return;
    }
    this.statusError = false;
    this.active = session.status === 'running';
  }

  async organizeModels(order: string[]): Promise<boolean> {
    if (!this.canOrganizeModels) return false;
    this.organizing = true;
    this.modelOperationError = null;
    try {
      await this.request(signal => organizeModels(order, signal), 120_000);
      await this.reload();
      if (this.catalog.state.status !== 'ready') throw new ApiError('invalid_response');
      return true;
    } catch (error) {
      this.modelOperationError = this.apiError(error);
      return false;
    } finally {
      this.organizing = false;
    }
  }

  async deleteModel(id: string): Promise<void> {
    if (!this.canDeleteModel || this.currentModelId !== id) return;
    this.organizing = true;
    this.modelOperationError = null;
    try {
      await this.request(signal => deleteModel(id, signal), 120_000);
    } catch (error) {
      this.modelOperationError = this.apiError(error);
    } finally {
      const { currentModelId: _discarded, ...remaining } = this.stagedConfiguration;
      this.stagedConfiguration = remaining;
      this.stagedModels = {};
      await Promise.all([this.catalog.reload(), this.refreshActive()]);
      this.organizing = false;
    }
  }

  async saveModelInfo(id: string, name: string, icon: File | null): Promise<boolean> {
    const model = this.currentModel;
    if (!this.canConfigure || !model || model.id !== id || model.status !== 'ready' || !name.trim()) return false;
    const extension = icon ? /\.(png|jpe?g|webp|gif|avif|bmp)$/i.exec(icon.name)?.[0].toLowerCase() : null;
    if (icon && (!extension || !icon.size || (icon.type && !icon.type.startsWith('image/')))) return false;
    this.modelInfoSaving = true;
    this.modelInfoError = null;
    try {
      await this.request(async signal => {
        const { session } = await readSessionState(signal);
        if (session.status === 'starting') throw new ApiError('starting');
        if (session.status === 'running') throw new ApiError('active');
        const updates: { name?: string; icon?: File } = {};
        if (icon && extension) updates.icon = icon;
        if (name !== model.name) updates.name = name;
        if (!updates.icon && updates.name === undefined) return;
        this.catalog.applyModel(await updateModelInfo(id, updates, signal));
      }, 120_000);
      return true;
    } catch (error) {
      this.modelInfoError = this.apiError(error);
      try { this.catalog.applyModel(await this.request(signal => readModel(id, signal))); } catch { /* Keep the draft for retry. */ }
      return false;
    } finally {
      this.modelInfoSaving = false;
    }
  }

  async uploadModel(model: File, index: File | null) {
    if (!this.canConfigure) return;
    this.uploadStatus = 'uploading';
    this.uploadError = null;
    this.uploadBytes = 0;
    this.uploadTotal = model.size + (index?.size ?? 0);
    const phase = { registering: false };
    try {
      await this.request(signal => importModel(model, index, signal,
        bytes => { this.uploadBytes = Math.min(bytes, this.uploadTotal); },
        () => { phase.registering = true; this.uploadStatus = 'registering'; }), 30 * 60_000);
      if (this.disposed) return;
      await this.catalog.reload();
      await this.refreshActive();
      if (!this.disposed) this.uploadStatus = this.catalog.state.status === 'ready' ? 'success' : 'refresh_failed';
    } catch (error) {
      if (!this.disposed) {
        this.uploadError = this.apiError(error);
        this.uploadStatus = phase.registering
          && (this.uploadError.code === 'network' || this.uploadError.code === 'timeout' || this.uploadError.code === 'invalid_response')
          ? 'uncertain' : 'error';
      }
    }
  }

  resetUpload() {
    if (!this.importing) { this.uploadStatus = 'idle'; this.uploadError = null; }
  }

  async reload() {
    if (this.disposed || this.deviceRescanning || this.isSaving || this.operation || this.dirty) return;
    this.saved = false;
    this.error = null;
    this.operationError = null;
    this.active = null;
    await Promise.all([this.catalog.reload(), this.refreshActive()]);
    if (!this.disposed && this.sessionState?.status === 'starting') {
      void this.followExternalStartup();
    }
  }

  private async followExternalStartup() {
    if (this.operation || this.disposed) return;
    this.operation = 'start';
    this.warmingUp = true;
    try {
      const settled = await this.waitForStartupSettlement();
      if (this.disposed) return;
      if (settled.status === 'stopped' && settled.lastError) {
        this.operationError = mapLastErrorToApiError(settled.lastError);
      }
      if (settled.status === 'running') void this.reconnectClientAudio(settled);
    } catch (error) {
      if (!this.disposed) this.operationError = this.apiError(error);
    } finally {
      this.warmingUp = false;
      this.operation = null;
    }
  }

  setGain(key: 'inputGain' | 'outputGain', value: number) {
    if (!this.canAdjustGain || !Number.isFinite(value) || value < 0 || value > 10) return;
    if (this.settings?.inputMode === 'client') {
      this.clientAudio.setGain(key, value);
      return;
    }
    if (this.settings?.[key] == null) return;
    if (this.settings[key] === value) return;
    this.edit({ [key]: value });
  }

  setNoiseGate(value: number) {
    if (!this.canAdjustNoiseGate || this.settings?.noiseGate == null || !Number.isInteger(value) || value < -100 || value > 0) return;
    if (value > -100) this.lastEnabledNoiseGate = value;
    else if (this.settings.noiseGate > -100) this.lastEnabledNoiseGate = this.settings.noiseGate;
    if (this.settings.noiseGate !== value) this.edit({ noiseGate: value });
  }

  setNoiseGateEnabled(enabled: boolean) {
    const current = this.settings?.noiseGate;
    if (!this.canAdjustNoiseGate || current == null || enabled === (current > -100)) return;
    if (!enabled && current > -100) this.lastEnabledNoiseGate = current;
    this.edit({ noiseGate: enabled ? this.lastEnabledNoiseGate : -100 }, true);
  }

  get realtimeDisplayEnabled(): boolean | null {
    const settings = this.settings;
    if (!settings || settings.ioAnalysisEnabled === null || settings.processAnalysisEnabled === null || settings.performanceMonitorEnabled === null) return null;
    if (!settings.ioAnalysisEnabled && !settings.processAnalysisEnabled) return false;
    if (settings.ioAnalysisEnabled && settings.processAnalysisEnabled && settings.performanceMonitorEnabled) return true;
    return null;
  }

  get canAdjustRealtimeDisplay() {
    const settings = this.settings;
    return this.catalog.state.status === 'ready' && !this.starting && settings?.ioAnalysisEnabled != null
      && settings.processAnalysisEnabled != null && settings.performanceMonitorEnabled != null
      && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation;
  }

  setRealtimeDisplay(enabled: boolean) {
    if (!this.canAdjustRealtimeDisplay || this.realtimeDisplayEnabled === enabled) return;
    this.edit({ ioAnalysisEnabled: enabled, processAnalysisEnabled: enabled, ...(enabled ? { performanceMonitorEnabled: true } : {}) }, true);
  }

  get canTogglePassThrough() {
    return this.catalog.state.status === 'ready' && this.active === true && !this.starting
      && this.settings?.inputMode != null && this.settings.passThrough !== null
      && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation;
  }

  togglePassThrough() {
    if (!this.canTogglePassThrough || !this.settings) return;
    this.edit({ passThrough: !this.settings.passThrough }, true);
  }

  get canToggleRecording() {
    const settings = this.settings;
    return this.catalog.state.status === 'ready' && settings?.inputMode != null && !this.starting
      && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation && !this.isSaving && !this.dirty
      && this.active !== null;
  }

  toggleRecording() {
    if (!this.canToggleRecording || !this.settings) return;
    this.recordingCompleted = null;
    this.recordingNotice = null;
    if (this.active === false) {
      this.recordingArmed = !this.recordingArmed;
      return;
    }
    const currentlyRecording = this.settings.recording === true;
    if (!currentlyRecording && this.recordingArmed) {
      this.recordingArmed = false;
      return;
    }
    this.recordingArmed = !currentlyRecording;
    this.edit({ recording: !currentlyRecording }, true);
  }

  setFilter(key: 'highPassEnabled' | 'lowPassEnabled', value: boolean): void;
  setFilter(key: 'highPassCutoff' | 'lowPassCutoff', value: number): void;
  setFilter(key: 'highPassEnabled' | 'lowPassEnabled' | 'highPassCutoff' | 'lowPassCutoff', value: boolean | number) {
    if (!this.canAdjustFilter || this.settings?.[key] == null || this.settings[key] === value) return;
    if (typeof value === 'number' && (!Number.isInteger(value) || value <= 0 || value > 15000)) return;
    this.edit({ [key]: value }, typeof value === 'boolean');
  }

  setModelValue(key: 'pitch' | 'indexRatio', value: number) {
    const model = this.currentModel;
    const settings = this.modelSettings;
    if (!this.canAdjustModel || !model || !settings || settings[key] === null || !Number.isFinite(value)) return;
    if (key === 'pitch' && (!settings.supportsPitch || !Number.isInteger(value) || value < -24 || value > 24)) return;
    if (key === 'indexRatio' && (!settings.hasIndex || value < 0 || value > 1)) return;
    if (settings[key] === value) return;
    this.modelDraft = { id: model.id, edits: { ...this.modelDraft?.edits, [key]: value } };
    this.saved = false;
    this.schedule();
  }

  setPitchEstimator(value: PitchEstimator) {
    const model = this.currentModel;
    if (!this.canConfigure || !this.settings?.inputMode || model?.status !== 'ready'
      || !model.settings?.supportsPitch || !this.modelSettings?.pitchEstimator || this.modelSettings.pitchEstimator === value) return;
    this.stageModel(model.id, { pitchEstimator: value });
  }

  selectModel(id: string) {
    if (!this.canConfigure || !this.catalog.models.some(model => model.id === id && model.status === 'ready')) return;
    if (id !== this.currentModelId) this.edit({ currentModelId: id }, true);
  }

  selectComputeDevice(id: number) {
    const devices = this.catalog.computeDeviceState;
    if (!this.canConfigure || !this.settings?.inputMode || this.settings.gpuDevice === null
      || devices.status !== 'ready' || !Number.isSafeInteger(id) || !devices.devices.some(device => device.id === id)
      || id === this.settings.gpuDevice) return;
    this.edit({ gpuDevice: id }, true);
  }

  async rescanAudioDevices() {
    if (!this.canConfigure || this.settings?.inputMode !== 'server') return;
    this.deviceRescanning = true;
    this.deviceRescanError = false;
    const previous = this.catalog.deviceState.status === 'ready' ? this.catalog.deviceState.devices : null;
    const selections = this.settings;
    let rescanStarted = false;
    try {
      const devices = await this.request(async signal => {
        const confirmed = await readSessionState(signal);
        if (confirmed.session.status !== 'stopped') {
          this.applySessionConfirmed(confirmed);
          throw new ApiError(confirmed.session.status === 'starting' ? 'starting' : 'active');
        }
        rescanStarted = true;
        return loadAudioDevices(signal, true);
      });
      if (this.disposed) return;
      for (const key of ['inputDevice', 'outputDevice', 'monitorDevice'] as const) {
        const id = selections[key];
        if (id == null || id < 0) continue;
        const direction = key === 'inputDevice' ? 'input' : 'output';
        const before = previous?.[direction].find(device => device.id === id);
        const after = devices[direction].find(device => device.id === id);
        if (!before || !after || before.name !== after.name || before.host !== after.host) {
          if (!this.devicesNeedingSelection.includes(key)) this.devicesNeedingSelection = [...this.devicesNeedingSelection, key];
        }
      }
      this.catalog.applyDevices(devices);
    } catch {
      if (!this.disposed) {
        this.deviceRescanError = true;
        if (rescanStarted) {
          this.catalog.invalidateDevices();
          this.devicesNeedingSelection = (['inputDevice', 'outputDevice', 'monitorDevice'] as const)
            .filter(key => selections[key] != null && selections[key]! >= 0);
        }
      }
    } finally {
      this.deviceRescanning = false;
    }
  }

  selectDevice(key: DeviceKey, id: number) {
    if (!this.canConfigure || this.settings?.inputMode !== 'server') return;
    const state = this.catalog.deviceState;
    if (state.status !== 'ready' || !Number.isSafeInteger(id)) return;
    const devices = key === 'inputDevice' ? state.devices.input : state.devices.output;
    if (id !== -1 && !devices.some(device => device.id === id)) return;
    if (id === this.settings[key] && !this.devicesNeedingSelection.includes(key)) return;
    const rateKey = `${key}Rate` as 'inputDeviceRate' | 'outputDeviceRate' | 'monitorDeviceRate';
    this.devicesNeedingSelection = this.devicesNeedingSelection.filter(device => device !== key);
    this.edit({ [key]: id, [rateKey]: -1 }, true);
  }

  useServerMode() {
    if (this.canConfigure && this.settings?.inputMode !== 'server') this.edit({ inputMode: 'server' }, true);
  }

  useClientMode() {
    if (this.canConfigure && this.settings?.inputMode !== 'client') {
      this.recordingArmed = false;
      this.edit({ inputMode: 'client' }, true);
      void this.clientAudio.refreshDevices().catch(() => {});
    }
  }

  setExtraSeconds(value: number) {
    if (!this.canConfigure || !this.settings?.inputMode || this.settings.extraSeconds == null
      || !Number.isFinite(value) || value < 0.01 || value > 2 || value === this.settings.extraSeconds) return;
    this.edit({ extraSeconds: value }, true);
  }

  setChunkSeconds(value: number) {
    const model = this.currentModel;
    if (!this.canConfigure || !this.settings?.inputMode || model?.status !== 'ready'
      || model.settings?.chunkSeconds == null || !Number.isFinite(value) || value < 0.05 || value > 5
      || value === this.modelSettings?.chunkSeconds) return;
    this.stageModel(model.id, { chunkSeconds: value });
  }

  private stageModel(id: string, edits: ModelEdits) {
    const model = this.catalog.models.find(item => item.id === id);
    if (!model?.settings) return;
    const merged = { ...this.stagedModels[id], ...edits };
    for (const key of Object.keys(merged) as (keyof ModelEdits)[]) {
      if (merged[key] === model.settings[key]) delete merged[key];
    }
    const all = { ...this.stagedModels };
    if (Object.keys(merged).length) all[id] = merged;
    else delete all[id];
    this.stagedModels = all;
  }

  private edit(edits: ConfigurationEdits, immediate = false) {
    const staged: ConfigurationEdits = {};
    const live: ConfigurationEdits = {};
    for (const [key, value] of Object.entries(edits)) {
      Object.assign(stagedKeys.includes(key as keyof ConfigurationEdits) ? staged : live, { [key]: value });
    }
    this.stagedConfiguration = { ...this.stagedConfiguration, ...staged };
    for (const key of Object.keys(this.stagedConfiguration) as (keyof ConfigurationEdits)[]) {
      const original = key === 'currentModelId'
        ? this.catalog.currentModelId
        : this.catalog.settings?.[key as keyof NonNullable<typeof this.catalog.settings>];
      if (this.stagedConfiguration[key] === original) delete this.stagedConfiguration[key];
    }
    if (!Object.keys(live).length) return;
    this.draft = { ...this.draft, ...live };
    this.saved = false;
    this.schedule(immediate);
  }

  flush() { this.schedule(true); }

  retry() {
    if (this.isSaving || this.operation || !this.dirty) return;
    this.error = null;
    this.schedule(true);
  }

  async discard() {
    if (this.isSaving || this.operation) return;
    clearTimeout(this.timer);
    this.draft = {};
    this.modelDraft = null;
    await this.reload();
  }

  private schedule(immediate = false) {
    if (!this.dirty) return;
    this.urgent ||= immediate;
    if (this.disposed || this.isSaving || this.operation || this.error) return;
    clearTimeout(this.timer);
    const delay = this.urgent ? 0 : Math.max(0, updateIntervalMs - (performance.now() - this.lastStarted));
    this.timer = setTimeout(() => { void this.save(); }, delay);
  }

  private save(): Promise<void> {
    if (this.flight) return this.flight;
    if (this.disposed || !this.dirty || this.error || this.operation) return Promise.resolve();
    this.isSaving = true;
    this.urgent = false;
    this.lastStarted = performance.now();
    const sent: PendingWrite = this.modelDraft && (this.nextWrite === 'model' || Object.keys(this.draft).length === 0)
      ? { kind: 'model', id: this.modelDraft.id, edits: { ...this.modelDraft.edits } }
      : { kind: 'configuration', edits: { ...this.draft } };
    this.nextWrite = sent.kind === 'model' ? 'configuration' : 'model';
    this.flight = this.persist(sent);
    return this.flight;
  }

  private async putLiveSessionWithRetry(
    edits: Partial<ConfigurationEdits & ModelEdits>,
    signal: AbortSignal,
  ): Promise<void> {
    const model = this.currentModel;
    const base = this.sessionState?.snapshot ?? this.catalog.settings;
    const modelId = this.sessionState?.snapshot?.modelId ?? model?.id;
    const modelSettings = model?.settings;
    if (!base || !modelId || !modelSettings) throw new ApiError('invalid_response');

    for (let attempt = 0; attempt < 2; attempt++) {
      const snap = this.sessionState?.snapshot ?? base;
      const payload = buildSessionPayload(
        snap,
        modelId,
        modelSettings,
        edits,
        (edits.recording ?? (snap as { recording?: boolean | null }).recording) ?? false,
      );
      try {
        const updated = await putSession(payload, signal, this.sessionEtag);
        if (this.disposed) return;
        this.applySessionConfirmed(updated);
        return;
      } catch (error) {
        if (attempt === 0 && error instanceof ApiError && error.code === 'etag_mismatch') {
          const refreshed = await readSessionState(signal);
          this.applySessionConfirmed(refreshed);
          if (refreshed.session.status === 'running') continue;
        }
        throw error;
      }
    }
  }

  private async persist(sent: PendingWrite) {
    try {
      if (sent.kind === 'configuration') {
        const { passThrough, recording, ...persistentEdits } = sent.edits;
        const hasSessionOnly = passThrough !== undefined || recording !== undefined;
        const hasPersistent = Object.keys(persistentEdits).length > 0;
        const hasFilterEdits = ['highPassEnabled', 'lowPassEnabled', 'highPassCutoff', 'lowPassCutoff']
          .some(key => key in persistentEdits);

        if (this.active === true && hasFilterEdits) {
          const fresh = await this.request(readSessionState, 8_000);
          if (this.disposed) return;
          this.applySessionConfirmed(fresh);
        }

        const sampleInputRate = this.active === true ? (this.sessionState?.inputSampleRate ?? null) : null;
        if (this.active === true && hasFilterEdits && this.sessionState?.snapshot) {
          const baseSnap = this.sessionState.snapshot;
          const high = persistentEdits.highPassCutoff ?? baseSnap.highPassCutoff;
          const low = persistentEdits.lowPassCutoff ?? baseSnap.lowPassCutoff;
          const highEnabled = persistentEdits.highPassEnabled ?? baseSnap.highPassEnabled ?? false;
          const lowEnabled = persistentEdits.lowPassEnabled ?? baseSnap.lowPassEnabled ?? false;
          validateFilterParameters(high, low, highEnabled, lowEnabled, sampleInputRate);
        }

        if (this.active === true && (hasSessionOnly || hasPersistent)) {
          await this.request(signal => this.putLiveSessionWithRetry(sent.edits, signal), 30_000);
          if (this.disposed) return;
          if (recording === false) await this.prepareRecordingDownload();
        } else if (hasSessionOnly) {
          throw new ApiError('active');
        }

        if (hasPersistent) {
          const timeoutMs = persistentEdits.gpuDevice !== undefined ? 120_000 : 30_000;
          const confirmed = await this.request(
            signal => updateSettings(persistentEdits, signal, { input: sampleInputRate }),
            timeoutMs,
          );
          if (this.disposed) return;
          this.catalog.applyConfiguration(confirmed);
          this.devicesNeedingSelection = this.devicesNeedingSelection.filter(key =>
            persistentEdits[key] === undefined
            || persistentEdits[key] !== this.draft[key]
            || confirmed.settings[key] !== persistentEdits[key]);
        }

        this.draft = Object.fromEntries(Object.entries(this.draft).filter(
          ([key, value]) => sent.edits[key as keyof ConfigurationEdits] !== value,
        ));
      } else {
        if (this.active === true && this.sessionState?.snapshot?.modelId === sent.id) {
          await this.request(signal => this.putLiveSessionWithRetry(sent.edits, signal), 30_000);
          if (this.disposed) return;
        }
        const confirmed = await this.request(signal => updateModelSettings(sent.id, sent.edits, signal));
        if (this.disposed) return;
        this.catalog.applyModel(confirmed);
        if (this.modelDraft?.id === sent.id) {
          const edits = Object.fromEntries(Object.entries(this.modelDraft.edits).filter(
            ([key, value]) => sent.edits[key as keyof ModelEdits] !== value,
          ));
          this.modelDraft = Object.keys(edits).length ? { id: sent.id, edits } : null;
        }
      }
      this.saved = !this.dirty;
    } catch (error) {
      if (!this.disposed) this.error = this.apiError(error);
    } finally {
      this.isSaving = false;
      this.flight = null;
      this.schedule();
    }
  }

  private async applyStagedSettings() {
    const selectedId = this.currentModelId;
    const ids = Object.keys(this.stagedModels);
    ids.sort((a, b) => (a === selectedId ? -1 : b === selectedId ? 1 : 0));

    for (const id of ids) {
      const edits = this.stagedModels[id];
      if (!edits || !Object.keys(edits).length) continue;
      const confirmed = await this.request(signal => updateModelSettings(id, edits, signal), 180_000);
      this.catalog.applyModel(confirmed);
      const remaining = { ...this.stagedModels };
      delete remaining[id];
      this.stagedModels = remaining;
    }

    const persistentConfig: ConfigurationEdits = { ...this.stagedConfiguration };
    if (this.catalog.settings?.wasapiExclusive === true) {
      persistentConfig.wasapiExclusive = false;
    }
    if (Object.keys(persistentConfig).length) {
      const confirmed = await this.request(signal => updateSettings(persistentConfig, signal), 180_000);
      this.catalog.applyConfiguration(confirmed);
      this.stagedConfiguration = {};
    }
  }

  private async waitForStartupSettlement(): Promise<SessionStateSnapshot> {
    const deadline = Date.now() + startupTimeoutMs;
    while (!this.disposed) {
      const current = this.sessionState;
      if (current && current.status !== 'starting') return current;
      if (Date.now() >= deadline) throw new ApiError('timeout');
      await new Promise(resolve => setTimeout(resolve, startupPollIntervalMs));
      if (this.disposed) throw new DOMException('Disposed', 'AbortError');
      const confirmed = await this.request(readSessionState, 8_000);
      if (this.disposed) throw new DOMException('Disposed', 'AbortError');
      this.applySessionConfirmed(confirmed);
      if (confirmed.session.status !== 'starting') return confirmed.session;
    }
    throw new DOMException('Disposed', 'AbortError');
  }

  private handleClientSuperseded() {
    this.clientAudio.stop();
    if (!this.disposed) {
      this.recordingNotice = 'superseded';
      void this.refreshActive();
    }
  }

  private handleClientClosed() {
    this.clientAudio.stop();
    if (!this.disposed) {
      void this.refreshActive();
    }
  }

  private handleClientFailure(error: Error) {
    this.clientAudio.stop();
    if (!this.disposed) {
      this.operationError = new ApiError('client_audio', undefined, error.message);
      void this.refreshActive();
    }
  }

  private async reconnectClientAudio(session: SessionStateSnapshot) {
    if (this.disposed || this.reconnecting || session.status !== 'running' || session.snapshot?.inputMode !== 'client') return;
    this.reconnecting = true;
    const version = ++this.reconnectVersion;
    try {
      const inputRate = session.inputSampleRate;
      const outputRate = session.outputSampleRate;
      if (!inputRate || !outputRate || inputRate <= 0 || outputRate <= 0) throw new ApiError('invalid_response');
      await this.clientAudio.prepareCapture(inputRate);
      if (this.disposed || version !== this.reconnectVersion) return;
      const confirmed = await this.request(readSessionState, 8_000);
      if (this.disposed || version !== this.reconnectVersion) return;
      this.applySessionConfirmed(confirmed);
      if (confirmed.session.status !== 'running' || confirmed.session.snapshot?.inputMode !== 'client'
        || confirmed.session.inputSampleRate !== inputRate || confirmed.session.outputSampleRate !== outputRate) {
        this.clientAudio.stop();
        return;
      }
      await this.clientAudio.connectStream(outputRate, {
        onSuperseded: () => this.handleClientSuperseded(),
        onClosed: () => this.handleClientClosed(),
        onFailure: err => this.handleClientFailure(err),
      });
    } catch (error) {
      if (!this.disposed && version === this.reconnectVersion) {
        this.handleClientFailure(error instanceof Error ? error : new Error('Audio connection failed.'));
      }
    } finally {
      this.reconnecting = false;
    }
  }

  async operate(operation: 'start' | 'stop') {
    if (this.disposed || (operation === 'start' ? !this.canStart : !this.canStop)) return;
    if (operation === 'stop') ++this.reconnectVersion;
    this.operation = operation;
    this.operationError = null;
    ++this.statusVersion;
    clearTimeout(this.timer);
    let capturePrepared = false;
    try {
      await this.flight;
      if (this.disposed) return;

      if (operation === 'start') {
        const latestSession = await this.request(readSessionState, 8_000);
        if (this.disposed) return;
        this.applySessionConfirmed(latestSession);
        if (latestSession.session.status === 'starting') throw new ApiError('starting');
        if (latestSession.session.status === 'running') throw new ApiError('active');

        const effectiveMode = this.settings?.inputMode;
        if (effectiveMode === 'client') {
          const inputRate = this.settings?.inputDeviceRate && this.settings.inputDeviceRate > 0
            ? this.settings.inputDeviceRate : 48000;
          await this.clientAudio.prepareCapture(inputRate);
          capturePrepared = true;
          if (this.disposed) {
            this.clientAudio.stop();
            return;
          }
        }

        this.warmingUp = true;
        await this.applyStagedSettings();
        if (this.disposed) return;

        const base = this.catalog.settings;
        const model = this.currentModel;
        if (!base || !model?.settings || !this.currentModelId) throw new ApiError('invalid_response');
        const payload = buildSessionPayload(
          base,
          this.currentModelId,
          model.settings,
          { wasapiExclusive: false },
          this.recordingArmed,
        );

        const initial = await this.request(
          signal => putSession(payload, signal, this.sessionEtag),
          120_000,
        );
        if (this.disposed) return;
        this.applySessionConfirmed(initial);

        const settled = initial.session.status === 'starting'
          ? await this.waitForStartupSettlement()
          : initial.session;
        if (this.disposed) return;

        if (settled.status !== 'running') {
          this.clientAudio.stop();
          capturePrepared = false;
          if (settled.lastError) throw mapLastErrorToApiError(settled.lastError);
          throw new ApiError('session_start_failed');
        }

        if (effectiveMode === 'client') {
          const outputRate = settled.outputSampleRate && settled.outputSampleRate > 0
            ? settled.outputSampleRate : 48000;
          try {
            await this.clientAudio.connectStream(outputRate, {
              onSuperseded: () => this.handleClientSuperseded(),
              onClosed: () => this.handleClientClosed(),
              onFailure: err => this.handleClientFailure(err),
            });
          } catch (error) {
            await this.request(signal => stopSession(signal, this.sessionEtag), 30_000)
              .then(stopped => { this.applySessionConfirmed(stopped); })
              .catch(() => {});
            throw error;
          }
        }
        this.statusError = false;
        return;
      }

      const wasRecording = this.sessionState?.snapshot?.recording === true;
      this.clientAudio.stop();
      const stopped = await this.request(async signal => {
        for (let attempt = 0; attempt < 2; attempt++) {
          try {
            return await stopSession(signal, this.sessionEtag);
          } catch (error) {
            if (attempt === 0 && error instanceof ApiError && error.code === 'etag_mismatch') {
              const refreshed = await readSessionState(signal);
              this.applySessionConfirmed(refreshed);
              if (refreshed.session.status === 'stopped') return refreshed;
              continue;
            }
            throw error;
          }
        }
        throw new ApiError('invalid_response');
      }, 30_000);
      if (this.disposed) return;
      this.applySessionConfirmed(stopped);
      if (wasRecording) {
        await this.prepareRecordingDownload();
      }
      this.statusError = false;
    } catch (error) {
      if (capturePrepared) this.clientAudio.stop();
      if (!this.disposed) {
        this.operationError = error instanceof ApiError ? error : this.settings?.inputMode === 'client' && operation === 'start'
          ? new ApiError('client_audio', undefined, error instanceof Error ? error.message : undefined)
          : this.apiError(error);
      }
    } finally {
      this.warmingUp = false;
      this.operation = null;
      if (!this.disposed) {
        await this.refreshActive();
        this.schedule();
      }
    }
  }

  private async prepareRecordingDownload() {
    try {
      const response = await fetch('/api/recordings/latest', { cache: 'no-store' });
      if (!response.ok) throw new Error('Recording download failed');
      const blob = await response.blob();
      const bytes = new DataView(await blob.arrayBuffer());
      if (bytes.byteLength < 12 || bytes.getUint32(0) !== 0x52494646 || bytes.getUint32(8) !== 0x57415645) throw new Error('Invalid WAV file');
      for (let offset = 12; offset + 8 <= bytes.byteLength;) {
        const size = bytes.getUint32(offset + 4, true);
        if (size > bytes.byteLength - offset - 8) throw new Error('Invalid WAV chunk');
        if (bytes.getUint32(offset) === 0x64617461) {
          if (size === 0) this.recordingNotice = 'empty';
          else this.recordingCompleted = blob;
          return;
        }
        offset += 8 + size + (size % 2);
      }
      throw new Error('Missing WAV data');
    } catch {
      this.recordingNotice = 'download_failed';
    }
  }

  private async refreshActive() {
    const version = ++this.statusVersion;
    try {
      const confirmed = await this.request(readSessionState, 8_000);
      if (!this.disposed && version === this.statusVersion) {
        this.applySessionConfirmed(confirmed);
      }
    } catch {
      if (!this.disposed && version === this.statusVersion) {
        this.sessionState = null;
        this.sessionEtag = null;
        this.active = null;
        this.statusError = true;
      }
    }
  }

  private schedulePoll() {
    if (this.disposed) return;
    this.poll = setTimeout(async () => {
      if (!this.operation && !this.isSaving) await this.refreshActive();
      this.schedulePoll();
    }, 2_000);
  }

  private async request<T>(task: (signal: AbortSignal) => Promise<T>, timeoutMs = 30_000): Promise<T> {
    const controller = new AbortController();
    this.requests.add(controller);
    const timeout = setTimeout(() => controller.abort('timeout'), timeoutMs);
    try { return await task(controller.signal); }
    catch (error) { throw controller.signal.reason === 'timeout' ? new ApiError('timeout') : error; }
    finally { clearTimeout(timeout); this.requests.delete(controller); }
  }

  private apiError(error: unknown) { return error instanceof ApiError ? error : new ApiError('network'); }

  dispose() {
    this.disposed = true;
    ++this.reconnectVersion;
    this.clientAudio.stop();
    ++this.statusVersion;
    clearTimeout(this.timer);
    clearTimeout(this.poll);
    for (const request of this.requests) request.abort();
    this.requests.clear();
  }
}

export function provideSession(catalog: ModelCatalogState) {
  return setContext(contextKey, new NativeSession(catalog));
}

export function useSession(): NativeSession {
  return getContext(contextKey);
}
